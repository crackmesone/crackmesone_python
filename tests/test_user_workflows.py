"""Integration tests for important authenticated user workflows."""

from app.models.notification import notification_add
from app.services.passhash import match_string


def test_user_can_change_password(alice_client, db, alice):
    response = alice_client.post('/change-password', data={
        'current_password': 'alice-password',
        'new_password': 'new-secure-password',
        'new_password_verify': 'new-secure-password',
    })

    assert response.status_code == 200
    assert response.data == b'Password has been successfully updated'
    updated = db.user.find_one({'name': 'alice'})
    assert match_string(updated['password'], 'new-secure-password') is True
    assert match_string(updated['password'], 'alice-password') is False


def test_password_change_rejects_wrong_current_password(alice_client, db, alice):
    original_hash = db.user.find_one({'name': 'alice'})['password']

    response = alice_client.post('/change-password', data={
        'current_password': 'incorrect',
        'new_password': 'new-secure-password',
        'new_password_verify': 'new-secure-password',
    })

    assert response.status_code == 401
    assert response.data == b'Current password is incorrect'
    assert db.user.find_one({'name': 'alice'})['password'] == original_hash


def test_password_change_validates_confirmation_and_length(alice_client, alice):
    mismatch = alice_client.post('/change-password', data={
        'current_password': 'alice-password',
        'new_password': 'first-password',
        'new_password_verify': 'second-password',
    })
    too_short = alice_client.post('/change-password', data={
        'current_password': 'alice-password',
        'new_password': 'short',
        'new_password_verify': 'short',
    })

    assert mismatch.status_code == 400
    assert mismatch.data == b'Passwords do not match'
    assert too_short.status_code == 400
    assert b'at least 8 characters' in too_short.data


def test_difficulty_rating_is_created_then_updated(
        alice_client, db, sample_crackme):
    path = f"/crackme/rate-diff/{sample_crackme['hexid']}"

    first = alice_client.post(path, data={'difficulty': '2'})
    second = alice_client.post(path, data={'difficulty': '6'})

    assert first.status_code == 302
    assert second.status_code == 302
    assert db.rating_difficulty.count_documents({}) == 1
    assert db.rating_difficulty.find_one({})['rating'] == 6
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['difficulty'] == 6.0


def test_multiple_quality_ratings_recalculate_average(
        alice_client, bob_client, db, sample_crackme):
    path = f"/crackme/rate-qual/{sample_crackme['hexid']}"

    assert alice_client.post(path, data={'quality': '2'}).status_code == 302
    assert bob_client.post(path, data={'quality': '6'}).status_code == 302

    assert db.rating_quality.count_documents({}) == 2
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['quality'] == 4.0


def test_invalid_rating_is_not_stored(alice_client, db, sample_crackme):
    response = alice_client.post(
        f"/crackme/rate-diff/{sample_crackme['hexid']}",
        data={'difficulty': '7'},
    )

    assert response.status_code == 500
    assert db.rating_difficulty.count_documents({}) == 0


def test_marking_notification_seen_is_idempotent(alice_client, db, alice):
    notification = notification_add('alice', 'A writeup was approved')
    assert db.user.find_one({'name': 'alice'})['unread_notifications'] == 1

    first = alice_client.post(
        '/notifications/mark-seen', data={'hexid': notification['hexid']}
    )
    second = alice_client.post(
        '/notifications/mark-seen', data={'hexid': notification['hexid']}
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert db.notifications.find_one({'hexid': notification['hexid']})['seen'] is True
    assert db.user.find_one({'name': 'alice'})['unread_notifications'] == 0


def test_user_cannot_modify_another_users_notification(
        alice_client, db, alice, bob):
    notification = notification_add('bob', 'Private notification')

    assert alice_client.post(
        '/notifications/mark-seen', data={'hexid': notification['hexid']}
    ).status_code == 200
    assert alice_client.post(
        '/notifications/delete', data={'hexid': notification['hexid']}
    ).status_code == 200

    stored = db.notifications.find_one({'hexid': notification['hexid']})
    assert stored is not None
    assert stored['seen'] is False


def test_notification_actions_require_an_identifier(alice_client, alice):
    assert alice_client.post('/notifications/mark-seen', data={}).status_code == 400
    assert alice_client.post('/notifications/delete', data={}).status_code == 400
