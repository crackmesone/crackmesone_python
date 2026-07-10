"""Reviewer workflow coverage for onsite writeups."""

import json

from app.controllers.solution import MIN_CONTENT_LENGTH
from app.models.solution import solution_create


def _content():
    return '# Review me\n\n' + ('Detailed analysis. ' * MIN_CONTENT_LENGTH)


def _pending_solution(db, sample_crackme, author='bob'):
    solution = solution_create(
        'Pending onsite writeup', author, sample_crackme, content=_content()
    )
    assert solution['visible'] is False
    return solution


def test_reviewer_routes_require_separate_reviewer_login(client, db):
    response = client.get('/review/dashboard')

    assert response.status_code == 302
    assert response.location == '/review/login'


def test_reviewer_login_requires_csrf(client, reviewer_account):
    response = client.post('/review/login', data={
        'username': 'reviewer',
        'password': 'reviewer-password',
    })

    assert response.status_code == 403


def test_reviewer_can_log_in_with_valid_credentials(client, reviewer_account):
    with client.session_transaction() as session:
        session['_reviewer_csrf_token'] = 'login-csrf'

    response = client.post('/review/login', data={
        'csrf_token': 'login-csrf',
        'username': 'reviewer',
        'password': 'reviewer-password',
    })

    assert response.status_code == 302
    assert response.location == '/review/dashboard'
    with client.session_transaction() as session:
        assert session['_reviewer_user'] == 'reviewer'
        assert session['_reviewer_is_admin'] is False


def test_pending_markdown_writeup_appears_in_review_queue(
        reviewer_client, db, sample_crackme, bob):
    solution = _pending_solution(db, sample_crackme)

    dashboard = reviewer_client.get('/review/dashboard')
    queue = reviewer_client.get('/review/reviewsolution')
    detail = reviewer_client.get(
        f"/review/viewsolution?solution_uuid={solution['hexid']}"
    )

    assert dashboard.status_code == 200
    assert b'Review solutions' in dashboard.data
    assert b'<h2 class="text-center"> 1 </h2>' in dashboard.data
    assert queue.status_code == 200
    assert solution['hexid'].encode() in queue.data
    assert b'Test Crackme' in queue.data
    assert detail.status_code == 200
    assert b'Pending onsite writeup' in detail.data
    assert json.dumps(_content()).encode() in detail.data
    assert b'Download attachment' not in detail.data


def test_approval_requires_valid_reviewer_csrf(
        reviewer_client, db, sample_crackme, bob):
    solution = _pending_solution(db, sample_crackme)

    response = reviewer_client.post('/review/approvesolution', data={
        'uuid': solution['hexid'],
        'csrf_token': 'wrong-token',
    })

    assert response.status_code == 403
    assert db.solution.find_one({'hexid': solution['hexid']})['visible'] is False


def test_reviewer_can_approve_markdown_only_writeup(
        reviewer_client, client, db, sample_crackme, bob, monkeypatch):
    from review import routes

    solution = _pending_solution(db, sample_crackme)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, 'notify_solution_approved', lambda *args: None)

    response = reviewer_client.post('/review/approvesolution', data={
        'uuid': solution['hexid'],
        'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    approved = db.solution.find_one({'hexid': solution['hexid']})
    assert approved['visible'] is True
    assert db.crackme.find_one({'_id': sample_crackme['_id']})['nbsolutions'] == 1
    assert db.notifications.count_documents({'user': 'bob'}) == 1
    assert db.notifications.count_documents({'user': 'alice'}) == 1
    assert client.get(f"/solution/{solution['hexid']}").status_code == 200
    assert client.get(f"/solution/{solution['hexid']}/content").status_code == 200


def test_reviewer_can_reject_writeup_with_reason(
        reviewer_client, db, sample_crackme, bob, monkeypatch):
    from review import routes

    solution = _pending_solution(db, sample_crackme)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *args, **kwargs: None)

    response = reviewer_client.post('/review/rejectsolution', data={
        'uuid': solution['hexid'],
        'reject_reason': '<b>Needs more explanation</b>',
        'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    assert db.solution.find_one({'hexid': solution['hexid']}) is None
    notification = db.notifications.find_one({'user': 'bob'})
    assert 'Needs more explanation' in notification['text']
    assert '<b>' not in notification['text']
    assert '&lt;b&gt;' in notification['text']


def test_approved_writeup_is_removed_from_pending_queue(
        reviewer_client, db, sample_crackme, bob, monkeypatch):
    from review import routes

    solution = _pending_solution(db, sample_crackme)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *args, **kwargs: None)
    monkeypatch.setattr(routes, 'notify_solution_approved', lambda *args: None)
    reviewer_client.post('/review/approvesolution', data={
        'uuid': solution['hexid'],
        'csrf_token': 'test-csrf-token',
    })

    queue = reviewer_client.get('/review/reviewsolution')

    assert solution['hexid'].encode() not in queue.data
