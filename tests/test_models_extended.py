"""Broader model coverage for queries, counters, cleanup, and state transitions."""

from datetime import datetime, timedelta, timezone

from bson import ObjectId


def test_crackme_query_counter_and_mutation_helpers(app, db, sample_crackme):
    from app.models import crackme

    crackme.crackme_increment_comments(sample_crackme['hexid'])
    crackme.crackme_decrement_comments(sample_crackme['hexid'])
    crackme.crackme_increment_downloads(sample_crackme['hexid'])
    crackme.crackme_set_float(sample_crackme['hexid'], 'quality', 5)
    assert crackme.count_crackmes_by_user('alice') == 1
    assert len(crackme.get_all_crackmes()) == 1
    assert len(crackme.crackmes_by_user('alice')) == 1
    assert crackme.crackme_by_user_and_name('alice', 'Test Crackme')['hexid'] == sample_crackme['hexid']
    stored = db.crackme.find_one({'_id': sample_crackme['_id']})
    assert stored['nbcomments'] == 0
    assert stored['nbdownloads'] == 1
    assert stored['quality'] == 5.0


def test_crackme_search_pagination_sort_and_random(app, db, sample_crackme):
    from app.models.crackme import random_crackmes, search_crackme

    for index in range(3):
        item = dict(sample_crackme)
        item['_id'] = ObjectId()
        item['hexid'] = str(item['_id'])
        item['name'] = f'Extra {index}'
        item['size'] = 1000 + index
        db.crackme.insert_one(item)
    results, has_more = search_crackme(page=1, per_page=2, sort_by='size', sort_order='asc')
    assert len(results) == 2
    assert has_more is True
    assert results[0]['size'] <= results[1]['size']
    assert len(random_crackmes(2)) == 2


def test_crackme_prepare_insert_update_and_delete(app, db):
    from app.models.crackme import (
        crackme_create_prepare, crackme_delete_by_hexid, crackme_insert,
        crackme_update, crackme_by_hexid_any,
    )

    item = crackme_create_prepare(
        'Prepared', 'Info', 'alice', 'C', 'x86', 'Linux', 20, 'file.bin'
    )
    crackme_insert(item)
    assert crackme_by_hexid_any(item['hexid'])['visible'] is False
    assert crackme_update(item['hexid'], {'info': 'Changed'}) == {
        'info': {'old': 'Info', 'new': 'Changed'}
    }
    assert crackme_update(item['hexid'], {'info': 'Changed'}) == {}
    crackme_delete_by_hexid(item['hexid'])
    assert db.crackme.count_documents({}) == 0


def test_comment_query_participant_and_spoiler_helpers(app, db, sample_crackme):
    from app.models.comment import (
        comment_by_id, comment_create, comment_set_spoiler,
        comments_by_user, count_comments_by_crackme, count_comments_by_user,
        get_thread_participants,
    )

    first = comment_create('First', 'alice', sample_crackme['hexid'])
    comment_create('Second', 'bob', sample_crackme['hexid'])
    assert count_comments_by_user('alice') == 1
    assert count_comments_by_crackme(sample_crackme['hexid']) == 2
    assert len(comments_by_user('alice')) == 1
    assert get_thread_participants(sample_crackme['hexid']) == {'alice', 'bob'}
    assert comment_by_id(str(first['_id']))['info'] == 'First'
    assert comment_set_spoiler(first['_id'], True)['spoiler'] is True


def test_solution_query_counter_and_author_helpers(app, db, sample_crackme):
    from app.models.solution import (
        count_solutions, count_solutions_by_crackme, count_solutions_by_user,
        get_solution_authors, solution_by_hexid, solution_create,
        solutions_by_crackme, solutions_by_user,
    )

    solution = solution_create('Info', 'bob', sample_crackme, content='body')
    db.solution.update_one({'_id': solution['_id']}, {'$set': {'visible': True}})
    assert count_solutions() == 1
    assert count_solutions_by_user('bob') == 1
    assert count_solutions_by_crackme(sample_crackme['hexid']) == 1
    assert solution_by_hexid(solution['hexid'])['author'] == 'bob'
    assert len(solutions_by_user('bob')) == 1
    assert len(solutions_by_crackme(sample_crackme['_id'])) == 1
    assert get_solution_authors(sample_crackme['hexid']) == {'bob'}


def test_notification_bulk_seen_remove_and_unseen_helpers(app, db, alice):
    from app.models.notification import (
        notification_add, notification_remove, notifications_by_user,
        notifications_has_unseen, notifications_set_seen,
    )

    first = notification_add('alice', 'First')
    second = notification_add('alice', 'Second')
    assert notifications_has_unseen('alice') is True
    items = notifications_by_user('alice')
    notifications_set_seen('alice', items)
    assert notifications_has_unseen('alice') is False
    assert db.user.find_one({'name': 'alice'})['unread_notifications'] == 0
    notification_remove('alice', first['hexid'])
    notification_remove('alice', second['hexid'])
    assert db.notifications.count_documents({}) == 0


def test_rating_query_update_and_delete_helpers(app, db, sample_crackme):
    from app.models.rating import (
        is_already_rated_difficulty, is_already_rated_quality,
        rating_difficulty_by_crackme, rating_difficulty_create,
        rating_difficulty_delete_by_crackme, rating_difficulty_set_rating,
        rating_quality_by_crackme, rating_quality_create,
        rating_quality_set_rating,
    )

    hexid = sample_crackme['hexid']
    rating_difficulty_create('alice', hexid, 2)
    rating_quality_create('alice', hexid, 3)
    rating_difficulty_set_rating('alice', hexid, 5)
    rating_quality_set_rating('alice', hexid, 6)
    assert is_already_rated_difficulty('alice', hexid) is True
    assert is_already_rated_quality('alice', hexid) is True
    assert rating_difficulty_by_crackme(hexid)[0]['rating'] == 5
    assert rating_quality_by_crackme(hexid)[0]['rating'] == 6
    rating_difficulty_delete_by_crackme(hexid)
    assert db.rating_difficulty.count_documents({}) == 0


def test_user_visibility_counts_password_and_notification_helpers(app, db, alice):
    from app.models.user import (
        all_users_visible, count_users, update_user_password, user_by_hexid,
        user_decrement_unread_notifications, user_get_unread_notifications,
        user_increment_unread_notifications,
    )

    db.user.update_one({'name': 'alice'}, {'$set': {'hexid': str(alice['_id'])}})
    assert count_users() == 1
    assert len(all_users_visible()) == 1
    assert user_by_hexid(str(alice['_id']))['name'] == 'alice'
    user_increment_unread_notifications('alice')
    assert user_get_unread_notifications('alice') == 1
    user_decrement_unread_notifications('alice', 20)
    assert user_get_unread_notifications('alice') == 0
    update_user_password('alice', 'new-hash')
    assert db.user.find_one({'name': 'alice'})['password'] == 'new-hash'


def test_expired_password_reset_cleanup(app, db):
    from app.models.password_reset import cleanup_expired_tokens

    db.password_reset_tokens.insert_many([
        {'token': 'old', 'expires_at': datetime.utcnow() - timedelta(hours=1)},
        {'token': 'new', 'expires_at': datetime.utcnow() + timedelta(hours=1)},
    ])
    cleanup_expired_tokens()
    assert db.password_reset_tokens.find_one({'token': 'old'}) is None
    assert db.password_reset_tokens.find_one({'token': 'new'}) is not None
