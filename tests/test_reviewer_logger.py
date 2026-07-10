"""Unit tests for reviewer audit logging and Discord delivery."""

from unittest.mock import MagicMock, patch

from review import logger


def test_successful_and_failed_operations_use_correct_log_levels():
    with patch.object(logger.logger, 'info') as info, \
         patch.object(logger.logger, 'error') as error:
        logger.init_logger(None)
        logger.log_reviewer_operation('approve_solution', 'reviewer', {'id': '1'})
        logger.log_reviewer_operation(
            'delete_solution', 'reviewer', {'id': '2'}, success=False
        )

    info.assert_called_once()
    error.assert_called_once()
    assert 'Status: SUCCESS' in info.call_args.args[0]
    assert 'Status: FAILED' in error.call_args.args[0]


def test_operation_logging_sends_configured_discord_webhook():
    logger.init_logger('https://discord.example.test/webhook')
    with patch.object(logger, 'send_discord_log') as send, \
         patch.object(logger.logger, 'info'):
        logger.log_reviewer_operation(
            'approve_solution', 'reviewer', {'solution': 'abc'}, True
        )

    send.assert_called_once_with(
        'approve_solution', 'reviewer', {'solution': 'abc'}, True
    )
    logger.init_logger(None)


def test_discord_log_payload_and_colors():
    logger.init_logger('https://discord.example.test/webhook')
    response = MagicMock(status_code=204)
    with patch.object(logger.requests, 'post', return_value=response) as post:
        logger.send_discord_log(
            'approve_solution', 'reviewer', {'solution': 'abc'}, True
        )

    url, = post.call_args.args
    payload = post.call_args.kwargs['json']['embeds'][0]
    assert url == 'https://discord.example.test/webhook'
    assert payload['color'] == 65280
    assert payload['fields'][0]['value'] == '✅ Success'
    assert '**solution:** abc' in payload['fields'][1]['value']
    logger.init_logger(None)


def test_discord_log_warns_on_http_failure_and_network_error():
    logger.init_logger('https://discord.example.test/webhook')
    with patch.object(
        logger.requests, 'post', return_value=MagicMock(status_code=500)
    ), patch.object(logger.logger, 'warning') as warning:
        logger.send_discord_log('delete_user', 'admin', {}, True)
        assert warning.called

    with patch.object(logger.requests, 'post', side_effect=TimeoutError), \
         patch.object(logger.logger, 'warning') as warning:
        logger.send_discord_log('other_action', 'admin', {}, False)
        assert warning.called
    logger.init_logger(None)
