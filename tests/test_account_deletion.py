"""Tests for the user-requested account deletion workflow."""


def _admin_client(app):
    from review import routes

    routes.users['admin'] = {
        'password_hash': routes.hash_string('admin-passwordtest-reviewer-salt'),
        'is_admin': True,
    }
    client = app.test_client()
    with client.session_transaction() as session:
        session['_reviewer_user'] = 'admin'
        session['_reviewer_is_admin'] = True
        session['_reviewer_csrf_token'] = 'admin-csrf'
    return client


# ---------------------------------------------------------------------------
# User-facing request creation
# ---------------------------------------------------------------------------

def test_user_can_request_account_deletion(alice_client, db):
    response = alice_client.post('/delete-account', data={
        'password': 'alice-password',
        'note': 'Leaving the site',
    })

    assert response.status_code == 200
    req = db.account_deletion_request.find_one({'requester': 'alice'})
    assert req is not None
    assert req['status'] == 'pending'
    assert req['email'] == 'alice@example.test'
    assert req['note'] == 'Leaving the site'


def test_deletion_request_requires_correct_password(alice_client, db):
    response = alice_client.post('/delete-account', data={
        'password': 'wrong-password',
    })

    assert response.status_code == 200
    assert db.account_deletion_request.count_documents({'requester': 'alice'}) == 0


def test_deletion_request_not_duplicated(alice_client, db):
    for _ in range(2):
        alice_client.post('/delete-account', data={'password': 'alice-password'})

    assert db.account_deletion_request.count_documents({
        'requester': 'alice', 'status': 'pending'
    }) == 1


def test_deletion_request_requires_login(client):
    response = client.post('/delete-account', data={'password': 'x'})
    # login_required redirects anonymous users away.
    assert response.status_code in (301, 302)


def test_delete_account_page_renders(alice_client):
    response = alice_client.get('/delete-account')
    assert response.status_code == 200
    assert b'Request account deletion' in response.data


# ---------------------------------------------------------------------------
# Reviewer / admin side
# ---------------------------------------------------------------------------

def test_reviewer_can_list_deletion_requests(reviewer_client, db):
    from app.models.account_deletion_request import account_deletion_request_create

    account_deletion_request_create('alice', 'alice@example.test')
    response = reviewer_client.get('/review/accountdeletionrequests')

    assert response.status_code == 200
    assert b'alice' in response.data


def test_admin_approves_deletion_and_emails_user(app, db, alice, monkeypatch):
    from review import routes
    from app.models.account_deletion_request import account_deletion_request_create

    req = account_deletion_request_create('alice', 'alice@example.test')

    sent = {}
    monkeypatch.setattr(
        routes, 'send_email',
        lambda to, subject, body: sent.update(to=to, subject=subject) or True
    )
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)

    client = _admin_client(app)
    response = client.post('/review/approveaccountdeletion', data={
        'uuid': req['hexid'], 'csrf_token': 'admin-csrf',
    })

    assert response.status_code == 302
    assert db.user.find_one({'name': 'alice'}) is None
    assert db.account_deletion_request.find_one(
        {'hexid': req['hexid']})['status'] == 'approved'
    assert sent['to'] == 'alice@example.test'
    routes.users.pop('admin', None)


def test_non_admin_cannot_approve_deletion(reviewer_client, db, alice):
    from app.models.account_deletion_request import account_deletion_request_create

    req = account_deletion_request_create('alice', 'alice@example.test')
    response = reviewer_client.post('/review/approveaccountdeletion', data={
        'uuid': req['hexid'], 'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 403
    # Account untouched, request still pending.
    assert db.user.find_one({'name': 'alice'}) is not None
    assert db.account_deletion_request.find_one(
        {'hexid': req['hexid']})['status'] == 'pending'


def test_reviewer_rejects_deletion_request(reviewer_client, db, alice):
    from review import routes
    from app.models.account_deletion_request import account_deletion_request_create

    req = account_deletion_request_create('alice', 'alice@example.test')

    response = reviewer_client.post('/review/rejectaccountdeletion', data={
        'uuid': req['hexid'],
        'reject_reason': 'Please contact us first',
        'csrf_token': 'test-csrf-token',
    })

    assert response.status_code == 302
    assert db.user.find_one({'name': 'alice'}) is not None
    assert db.account_deletion_request.find_one(
        {'hexid': req['hexid']})['status'] == 'rejected'
    # Requester is notified.
    assert db.notifications.count_documents({'user': 'alice'}) == 1
