"""Authorization and mutation tests for reviewer administration."""


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


def test_regular_reviewer_cannot_manage_reviewer_accounts(reviewer_client):
    assert reviewer_client.get('/review/managereviewers').status_code == 403


def test_admin_can_add_reviewer(app, db, monkeypatch):
    from review import routes

    client = _admin_client(app)
    monkeypatch.setattr(routes, 'save_users', lambda: None)
    monkeypatch.setattr(routes, 'log_reviewer_operation', lambda *a, **k: None)

    response = client.post('/review/managereviewers', data={
        'csrf_token': 'admin-csrf',
        'action': 'add',
        'new_username': 'new-reviewer',
        'new_password': 'reviewer-secret',
    })

    assert response.status_code == 200
    assert b"Reviewer &#39;new-reviewer&#39; added successfully" in response.data
    assert routes.users['new-reviewer']['is_admin'] is False
    assert routes.users['new-reviewer']['password_hash'] == routes.hash_string(
        'reviewer-secrettest-reviewer-salt'
    )
    routes.users.pop('new-reviewer', None)
    routes.users.pop('admin', None)


def test_admin_management_post_requires_csrf(app, db):
    from review import routes

    client = _admin_client(app)
    response = client.post('/review/managereviewers', data={'action': 'add'})

    assert response.status_code == 403
    routes.users.pop('admin', None)


def test_admin_cannot_delete_own_reviewer_account(app, db, monkeypatch):
    from review import routes

    client = _admin_client(app)
    monkeypatch.setattr(routes, 'save_users', lambda: None)
    response = client.post('/review/managereviewers', data={
        'csrf_token': 'admin-csrf',
        'action': 'delete',
        'username_to_delete': 'admin',
    })

    assert response.status_code == 200
    assert b'cannot delete your own account' in response.data
    assert 'admin' in routes.users
    routes.users.pop('admin', None)
