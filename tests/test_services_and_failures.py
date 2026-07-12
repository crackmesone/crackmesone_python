"""Service integration boundaries and injected controller failure paths."""

from unittest.mock import MagicMock, patch

import pytest


def test_discord_configuration_and_webhook_delivery(app):
    from app.services import discord

    config = {
        'Enabled': True,
        'WebhookPublic': 'https://discord.test/public',
        'WebhookPrivate': 'https://discord.test/private',
        'WebhookModeration': 'https://discord.test/moderation',
    }
    discord.init_discord(app, config)
    assert discord.get_public_webhook().endswith('/public')
    assert discord.get_private_webhook().endswith('/private')
    assert discord.get_moderation_webhook().endswith('/moderation')
    with patch.object(
        discord.requests, 'post', return_value=MagicMock(status_code=204)
    ) as post:
        assert discord.send_to_webhook('https://discord.test/hook', message='hello') is True
        assert post.call_args.kwargs['json']['content'] == 'hello'
    with patch.object(discord.requests, 'post', side_effect=TimeoutError):
        assert discord.send_to_webhook('https://discord.test/hook', message='hello') is False
    assert discord.send_to_webhook('', message='hello') is False
    discord.init_discord(app, {'Enabled': False})


def test_discord_notification_payload_builders(app):
    from app.services import discord

    discord.init_discord(app, {'Enabled': True, 'WebhookModeration': 'hook'})
    with patch.object(discord, 'send_moderation_notification', return_value=True) as send:
        assert discord.notify_new_comment(
            'alice', 'Challenge', 'abc', 'x' * 600,
            comment_id='comment', spoiler_token='token',
        ) is True
        embed = send.call_args.args[0]
        assert embed['fields'][2]['value'].endswith('...')
        assert any(field['name'] == 'Actions' for field in embed['fields'])
        discord.notify_spoiler_toggle('alice', 'Challenge', 'abc', 'bob', True)
        assert 'Marked As Spoiler' in send.call_args.args[0]['title']
        discord.notify_password_reset_request('alice@example.test')
        assert send.call_args.args[0]['title'] == 'Password Reset Requested'
        discord.notify_password_reset_complete('alice', 'alice@example.test')
        assert send.call_args.args[0]['title'] == 'Password Reset Completed'
    discord.init_discord(app, {'Enabled': False})


def test_pending_discord_notifications_use_private_channel(app):
    from app.services import discord

    discord.init_discord(app, {'Enabled': True})
    with patch.object(discord, 'send_private_notification', return_value=True) as send:
        assert discord.notify_new_crackme('alice', 'Challenge') is True
        assert send.call_args.kwargs['embed']['title'] == 'Pending Crackme Submission'
        assert discord.notify_new_solution('bob', 'Challenge') is True
        assert send.call_args.kwargs['embed']['title'] == 'Pending Solution Submission'
    discord.init_discord(app, {'Enabled': False})


@pytest.mark.parametrize('error,expected', [
    (None, None),
    (RuntimeError('no documents'), 'ErrNoResult'),
    (RuntimeError('not found'), 'ErrNoResult'),
    (RuntimeError('other'), 'RuntimeError'),
])
def test_standardize_database_errors(error, expected):
    from app.models.errors import standardize_error
    result = standardize_error(error)
    assert (type(result).__name__ if result is not None else None) == expected


def test_password_hash_matching_rejects_malformed_hashes():
    from app.services.passhash import match_bytes, match_string
    assert match_string('not-a-hash', 'password') is False
    assert match_string(None, 'password') is False
    assert match_bytes(b'not-a-hash', b'password') is False
    assert match_bytes(None, b'password') is False


def test_notification_controller_database_failures(alice_client, alice):
    with patch(
        'app.controllers.notifications.notifications_by_user', side_effect=RuntimeError
    ):
        page = alice_client.get('/notifications')
    with patch(
        'app.controllers.notifications.notification_mark_seen_single',
        side_effect=RuntimeError,
    ):
        seen = alice_client.post('/notifications/mark-seen', data={'hexid': 'x'})
    with patch(
        'app.controllers.notifications.notification_remove', side_effect=RuntimeError
    ):
        deleted = alice_client.post('/notifications/delete', data={'hexid': 'x'})
    assert page.status_code == 200
    assert seen.status_code == deleted.status_code == 500


def test_password_change_hash_and_update_failures(alice_client, alice):
    payload = {
        'current_password': 'alice-password',
        'new_password': 'replacement-password',
        'new_password_verify': 'replacement-password',
    }
    with patch('app.controllers.password.hash_string', side_effect=RuntimeError):
        hashing = alice_client.post('/change-password', data=payload)
    with patch('app.controllers.password.update_user_password', side_effect=RuntimeError):
        updating = alice_client.post('/change-password', data=payload)
    assert hashing.status_code == 500
    assert updating.status_code == 500


def test_rating_missing_fields_and_database_failure(alice_client, sample_crackme):
    diff_path = f"/crackme/rate-diff/{sample_crackme['hexid']}"
    qual_path = f"/crackme/rate-qual/{sample_crackme['hexid']}"
    assert alice_client.post(diff_path, data={}).status_code == 302
    assert alice_client.post(qual_path, data={}).status_code == 302
    with patch(
        'app.controllers.rating.is_already_rated_difficulty', side_effect=RuntimeError
    ):
        assert alice_client.post(diff_path, data={'difficulty': '3'}).status_code == 500
    with patch(
        'app.controllers.rating.is_already_rated_quality', side_effect=RuntimeError
    ):
        assert alice_client.post(qual_path, data={'quality': '3'}).status_code == 500


def test_search_show_all_and_database_failure(client):
    with patch('app.controllers.search.search_crackme', return_value=([], False)) as search:
        response = client.post('/search', data={
            'show_all': '1', 'size-min': '2', 'size-min-unit': 'GB',
            'size-max': '3', 'size-max-unit': 'KB',
        })
    assert response.status_code == 200
    assert search.call_args.kwargs['per_page'] == 10000
    assert search.call_args.kwargs['size_min'] == 2 * 1024**3
    assert search.call_args.kwargs['size_max'] == 3 * 1024
    with patch('app.controllers.search.search_crackme', side_effect=RuntimeError):
        assert client.post('/search', data={}).status_code == 200


def test_random_search_database_unavailable(client):
    from app.models.errors import ErrUnavailable
    with patch('app.controllers.search.random_crackmes', side_effect=ErrUnavailable):
        response = client.get('/random')
    assert response.status_code == 200
