"""Coverage of the narrowly scoped, reversible orphan cleanup utility."""

import os
import time

from bson import ObjectId
from pymongo.errors import ConnectionFailure
import pytest

from script.cleanup_orphaned_pending_files import cleanup_orphaned_files


def _file(root, directory, name=None, old=True):
    path = root / directory / (name or str(ObjectId()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'original upload')
    if old:
        timestamp = time.time() - 3600
        os.utime(path, (timestamp, timestamp))
    return path


def test_cleanup_quarantines_only_old_orphans_and_is_repeatable(db, tmp_path):
    orphan = _file(tmp_path, 'tmp/crackme')
    source = _file(tmp_path, 'private/crackme_source', orphan.name)
    solution = _file(tmp_path, 'tmp/solution')
    source_only = _file(tmp_path, 'private/crackme_source')
    orphans = [orphan, source, solution, source_only]
    preserved = [
        _file(tmp_path, 'tmp/crackme', old=False),
        _file(tmp_path, 'tmp/solution', 'notes.txt'),
        _file(tmp_path, 'static/crackme', str(ObjectId()) + '.zip'),
    ]
    for kind in ('crackme', 'solution'):
        for visible in (True, False):
            valid = _file(tmp_path, f'tmp/{kind}')
            db[kind].insert_one({'_id': ObjectId(valid.name), 'visible': visible})
            preserved.append(valid)
    directory = tmp_path / 'tmp/crackme' / str(ObjectId())
    directory.mkdir()
    link = tmp_path / 'tmp/crackme' / str(ObjectId())
    link.symlink_to(orphan)

    affected, quarantine = cleanup_orphaned_files(db, tmp_path)
    assert set(affected) == {p.relative_to(tmp_path) for p in orphans}
    assert quarantine is None
    assert not (tmp_path / 'private/orphaned_submissions').exists()
    assert all(p.exists() for p in orphans + preserved)

    affected, quarantine = cleanup_orphaned_files(db, tmp_path, apply=True)
    assert set(affected) == {p.relative_to(tmp_path) for p in orphans}
    assert quarantine.is_relative_to(tmp_path / 'private/orphaned_submissions')
    assert all(not p.exists() for p in orphans)
    assert all((quarantine / p.relative_to(tmp_path)).read_bytes() == b'original upload'
               for p in orphans)
    assert all(p.read_bytes() == b'original upload' for p in preserved)
    assert directory.is_dir()
    assert link.is_symlink()
    assert db.crackme.count_documents({}) == db.solution.count_documents({}) == 2
    assert cleanup_orphaned_files(db, tmp_path, apply=True) == ([], None)


def test_cleanup_does_not_move_files_when_database_query_fails(db, tmp_path, monkeypatch):
    orphan = _file(tmp_path, 'tmp/crackme')

    def unavailable(*args, **kwargs):
        raise ConnectionFailure('database unavailable')

    monkeypatch.setattr(db.crackme, 'find_one', unavailable)
    with pytest.raises(ConnectionFailure):
        cleanup_orphaned_files(db, tmp_path, apply=True)
    assert orphan.exists()
    assert not (tmp_path / 'private/orphaned_submissions').exists()
