"""Integration coverage for onsite Markdown solution writeups."""

import base64
from io import BytesIO
from itertools import cycle

import pytest

from app.controllers.solution import MAX_CONTENT_LENGTH, MIN_CONTENT_LENGTH
from app.models.solution import solution_create
from app.services.crypto import get_obfuscation_key_base64


def _markdown(length=MIN_CONTENT_LENGTH):
    prefix = '# Analysis\n\nThe challenge validates its input using this algorithm.\n\n'
    return prefix + ('A' * max(0, length - len(prefix)))


def _submit(client, crackme, **data):
    return client.post(
        f"/upload/solution/{crackme['hexid']}",
        data=data,
        content_type='multipart/form-data',
    )


def _approved_solution(db, sample_crackme, **overrides):
    values = {
        'info': 'A useful summary',
        'username': 'alice',
        'crackme': sample_crackme,
        'content': _markdown(),
        'original_filename': None,
    }
    values.update(overrides)
    solution = solution_create(**values)
    db.solution.update_one(
        {'hexid': solution['hexid']},
        {'$set': {'visible': True}},
    )
    solution['visible'] = True
    return solution


def test_authenticated_user_can_open_writeup_editor(alice_client, sample_crackme):
    response = alice_client.get(f"/upload/solution/{sample_crackme['hexid']}")

    assert response.status_code == 200
    assert b'Writeup (Markdown)' in response.data
    assert str(MIN_CONTENT_LENGTH).encode() in response.data
    assert f'{MAX_CONTENT_LENGTH:,}'.encode() in response.data


def test_legacy_editor_url_redirects_to_primary_editor(alice_client, sample_crackme):
    response = alice_client.get(
        f"/upload/solution/{sample_crackme['hexid']}/editor"
    )

    assert response.status_code == 302
    assert response.location == f"/upload/solution/{sample_crackme['hexid']}"


def test_markdown_only_writeup_is_created_pending_review(
        alice_client, db, sample_crackme):
    content = _markdown()
    response = _submit(
        alice_client,
        sample_crackme,
        info='Solved with static analysis',
        content=content,
    )

    assert response.status_code == 200
    assert b'waiting' in response.data.lower() or b'success' in response.data.lower()
    solution = db.solution.find_one({'author': 'alice'})
    assert solution['content'] == content
    assert solution['original_filename'] is None
    assert solution['has_attachment'] is False
    assert solution['visible'] is False


@pytest.mark.parametrize(
    ('content', 'message'),
    [
        ('', b'Please write a markdown writeup or attach a file'),
        ('A' * (MIN_CONTENT_LENGTH - 1), b'writeup is too short'),
        ('A' * (MAX_CONTENT_LENGTH + 1), b'exceeds the maximum length'),
    ],
)
def test_invalid_writeup_content_is_rejected(
        alice_client, db, sample_crackme, content, message):
    response = _submit(
        alice_client,
        sample_crackme,
        info='Summary',
        content=content,
    )

    assert response.status_code == 302
    with alice_client.session_transaction() as session:
        assert message in session['_flashes'][-1][1].encode()
    assert db.solution.count_documents({}) == 0


def test_writeup_at_maximum_length_is_accepted(alice_client, db, sample_crackme):
    content = _markdown(MAX_CONTENT_LENGTH)

    assert len(content) == MAX_CONTENT_LENGTH
    assert _submit(
        alice_client, sample_crackme, info='Summary', content=content
    ).status_code == 200
    assert db.solution.find_one({})['content'] == content


def test_duplicate_writeup_is_rejected(alice_client, db, sample_crackme):
    first = _submit(
        alice_client, sample_crackme, info='First', content=_markdown()
    )
    second = _submit(
        alice_client, sample_crackme, info='Second', content=_markdown()
    )

    assert first.status_code == 200
    assert second.status_code == 302
    assert db.solution.count_documents({'author': 'alice'}) == 1
    with alice_client.session_transaction() as session:
        assert "already submitted" in session['_flashes'][-1][1]


def test_writeup_with_attachment_records_and_writes_attachment(
        alice_client, db, sample_crackme, tmp_path, monkeypatch):
    from app.controllers import solution as solution_controller

    monkeypatch.setattr(solution_controller, 'UPLOAD_FOLDER', str(tmp_path))
    response = _submit(
        alice_client,
        sample_crackme,
        info='Includes a helper script',
        content=_markdown(),
        file=(BytesIO(b'print("helper")\n'), '../../helper.py'),
    )

    assert response.status_code == 200
    solution = db.solution.find_one({'author': 'alice'})
    assert solution['original_filename'] == 'helper.py'
    assert solution['has_attachment'] is True
    assert (tmp_path / solution['hexid']).read_bytes() == b'print("helper")\n'


def test_approved_onsite_writeup_page_does_not_embed_raw_markdown(
        client, db, sample_crackme):
    content = _markdown()
    solution = _approved_solution(db, sample_crackme, content=content)

    response = client.get(f"/solution/{solution['hexid']}")

    assert response.status_code == 200
    assert b'Loading writeup' in response.data
    assert content.encode() not in response.data
    assert b"fetch('/solution/' + hexid + '/content')" in response.data


def test_content_endpoint_returns_decodable_obfuscated_markdown(
        client, app, db, sample_crackme):
    content = _markdown() + '\n```python\nprint("solved")\n```'
    solution = _approved_solution(db, sample_crackme, content=content)

    response = client.get(f"/solution/{solution['hexid']}/content")

    assert response.status_code == 200
    assert response.mimetype == 'application/octet-stream'
    assert content.encode() not in response.data
    salt = app.config['APP_CONFIG']['Writeup']['ObfuscationSalt']
    key = base64.b64decode(get_obfuscation_key_base64(solution['hexid'], salt))
    decoded = bytes(value ^ key_byte for value, key_byte in zip(response.data, cycle(key)))
    assert decoded.decode() == content


def test_attachment_only_solution_has_no_content_endpoint(
        client, db, sample_crackme):
    solution = _approved_solution(
        db,
        sample_crackme,
        content=None,
        original_filename='analysis.pdf',
    )

    page = client.get(f"/solution/{solution['hexid']}")
    content = client.get(f"/solution/{solution['hexid']}/content")

    assert page.status_code == 200
    assert b'This writeup is only available for download' in page.data
    assert b'Download Archive' in page.data
    assert content.status_code == 404


def test_pending_writeup_is_not_public(client, db, sample_crackme):
    solution = solution_create(
        'Summary', 'alice', sample_crackme, content=_markdown()
    )

    assert client.get(f"/solution/{solution['hexid']}").status_code == 404
    assert client.get(f"/solution/{solution['hexid']}/content").status_code == 404
