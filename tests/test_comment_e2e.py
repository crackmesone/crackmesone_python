"""End-to-end integration tests for the full comment lifecycle:
creation, UI rendering, editing, UI update, profile sync, deletion, and permission boundaries.
"""

from app.models.comment import comment_create


def test_full_comment_lifecycle_end_to_end(alice_client, bob_client, client, db, sample_crackme, bob, alice):
    hexid = sample_crackme['hexid']

    # 1. Anonymous visitor views crackme comments before any comment is posted
    resp = client.get(f"/crackme/{hexid}")
    assert resp.status_code == 200
    html = resp.data.decode('utf-8')
    assert "Comments (0)" in html
    assert "You must be logged in to post a comment" in html
    assert "modal-edit-comment" in html

    # 2. Bob logs in and posts a comment
    post_resp = bob_client.post(f"/comment/{hexid}", data={
        'comment': 'Initial comment with a typo: Great crackeme!'
    }, follow_redirects=True)
    assert post_resp.status_code == 200
    post_html = post_resp.data.decode('utf-8')
    assert "Comment uploaded!" in post_html

    # Verify database state after creation
    comment = db.comment.find_one({'author': 'bob', 'crackmehexid': hexid})
    assert comment is not None
    comment_id = str(comment['_id'])
    assert comment['info'] == 'Initial comment with a typo: Great crackeme!'
    assert comment.get('edited') is not True

    crackme_doc = db.crackme.find_one({'hexid': hexid})
    assert crackme_doc['nbcomments'] == 1

    # 3. Verify Bob sees the Edit and Delete controls for his comment on the crackme page
    bob_view = bob_client.get(f"/crackme/{hexid}")
    assert bob_view.status_code == 200
    bob_html = bob_view.data.decode('utf-8')
    assert f"openEditCommentModal('{comment_id}')" in bob_html
    assert f'action="/comment/{comment_id}/delete"' in bob_html
    assert f'id="comment-raw-{comment_id}"' in bob_html
    assert "Initial comment with a typo: Great crackeme!" in bob_html
    assert "(edited)" not in bob_html

    # 4. Verify Alice (crackme author, but not comment author) does NOT see edit or delete buttons for Bob's comment
    alice_view = alice_client.get(f"/crackme/{hexid}")
    assert alice_view.status_code == 200
    alice_html = alice_view.data.decode('utf-8')
    assert f"openEditCommentModal('{comment_id}')" not in alice_html
    assert f'action="/comment/{comment_id}/delete"' not in alice_html
    assert f'action="/comment/{comment_id}/spoiler"' in alice_html  # Crackme author can toggle spoiler

    # 5. Verify Anonymous user does NOT see edit or delete buttons
    anon_view = client.get(f"/crackme/{hexid}")
    assert anon_view.status_code == 200
    anon_html = anon_view.data.decode('utf-8')
    assert f"openEditCommentModal('{comment_id}')" not in anon_html
    assert f'action="/comment/{comment_id}/delete"' not in anon_html

    # 6. Verify Bob's profile reflects the comment
    bob_profile = client.get('/user/bob')
    assert bob_profile.status_code == 200
    profile_html = bob_profile.data.decode('utf-8')
    assert "Initial comment with a typo: Great crackeme!" in profile_html

    # 7. Bob edits his comment to fix the typo
    edit_resp = bob_client.post(f"/comment/{comment_id}/edit", data={
        'comment': 'Updated comment: Great crackme! Solved in Ghidra.'
    }, follow_redirects=True)
    assert edit_resp.status_code == 200
    edit_html = edit_resp.data.decode('utf-8')
    assert "Comment updated!" in edit_html

    # Verify database state after edit
    updated_comment = db.comment.find_one({'_id': comment['_id']})
    assert updated_comment['info'] == 'Updated comment: Great crackme! Solved in Ghidra.'
    assert updated_comment['edited'] is True
    assert updated_comment['updated_at'] is not None

    # 8. Verify the crackme page now shows the updated text and the (edited) indicator
    view_after_edit = client.get(f"/crackme/{hexid}")
    assert view_after_edit.status_code == 200
    after_edit_html = view_after_edit.data.decode('utf-8')
    assert "Updated comment: Great crackme! Solved in Ghidra." in after_edit_html
    assert "(edited)" in after_edit_html
    assert "Initial comment with a typo" not in after_edit_html

    # Verify raw textarea for edit modal also contains the updated text
    assert f'id="comment-raw-{comment_id}" style="display: none;">Updated comment: Great crackme! Solved in Ghidra.</textarea>' in after_edit_html

    # 9. Verify Bob's profile reflects the edited comment
    bob_profile_after_edit = client.get('/user/bob')
    assert "Updated comment: Great crackme! Solved in Ghidra." in bob_profile_after_edit.data.decode('utf-8')

    # 10. Negative tests: unauthorized attempts
    # Alice attempts to edit Bob's comment
    alice_edit_attempt = alice_client.post(f"/comment/{comment_id}/edit", data={
        'comment': 'Hacked by Alice'
    }, follow_redirects=True)
    assert "You can only edit your own comments." in alice_edit_attempt.data.decode('utf-8')

    # Alice attempts to delete Bob's comment
    alice_delete_attempt = alice_client.post(f"/comment/{comment_id}/delete", follow_redirects=True)
    assert "You can only delete your own comments." in alice_delete_attempt.data.decode('utf-8')

    # Comment is still intact in DB
    assert db.comment.count_documents({'_id': comment['_id']}) == 1
    assert db.crackme.find_one({'hexid': hexid})['nbcomments'] == 1

    # Bob attempts to submit empty edit
    bob_empty_edit = bob_client.post(f"/comment/{comment_id}/edit", data={
        'comment': '   '
    }, follow_redirects=True)
    assert "Comment cannot be empty." in bob_empty_edit.data.decode('utf-8')

    # 11. Bob deletes his own comment
    delete_resp = bob_client.post(f"/comment/{comment_id}/delete", follow_redirects=True)
    assert delete_resp.status_code == 200
    delete_html = delete_resp.data.decode('utf-8')
    assert "Comment deleted." in delete_html

    # 12. Verify DB and UI after deletion
    # Comment is gone from DB
    assert db.comment.find_one({'_id': comment['_id']}) is None
    # Crackme counter decremented back to 0
    assert db.crackme.find_one({'hexid': hexid})['nbcomments'] == 0

    # Crackme page no longer displays the comment
    final_crackme_view = client.get(f"/crackme/{hexid}")
    final_crackme_html = final_crackme_view.data.decode('utf-8')
    assert "Updated comment: Great crackme!" not in final_crackme_html
    assert f"openEditCommentModal('{comment_id}')" not in final_crackme_html
    assert "Comments (0)" in final_crackme_html

    # Bob's profile shows 0 comments and no comment row
    final_profile_view = client.get('/user/bob')
    final_profile_html = final_profile_view.data.decode('utf-8')
    assert "Updated comment: Great crackme!" not in final_profile_html


def test_multi_comment_isolation_and_cascade_delete(alice_client, bob_client, client, db, sample_crackme, bob, alice):
    hexid = sample_crackme['hexid']

    # Alice posts comment 1
    alice_client.post(f"/comment/{hexid}", data={'comment': 'Alice comment'})
    c1 = db.comment.find_one({'author': 'alice', 'crackmehexid': hexid})
    c1_id = str(c1['_id'])

    # Bob posts comment 2
    bob_client.post(f"/comment/{hexid}", data={'comment': 'Bob comment'})
    c2 = db.comment.find_one({'author': 'bob', 'crackmehexid': hexid})
    c2_id = str(c2['_id'])

    assert db.crackme.find_one({'hexid': hexid})['nbcomments'] == 2

    # Alice views page: Alice can edit/delete c1, but NOT c2
    alice_html = alice_client.get(f"/crackme/{hexid}").data.decode('utf-8')
    assert f"openEditCommentModal('{c1_id}')" in alice_html
    assert f'action="/comment/{c1_id}/delete"' in alice_html
    assert f"openEditCommentModal('{c2_id}')" not in alice_html
    assert f'action="/comment/{c2_id}/delete"' not in alice_html

    # Bob views page: Bob can edit/delete c2, but NOT c1
    bob_html = bob_client.get(f"/crackme/{hexid}").data.decode('utf-8')
    assert f"openEditCommentModal('{c2_id}')" in bob_html
    assert f'action="/comment/{c2_id}/delete"' in bob_html
    assert f"openEditCommentModal('{c1_id}')" not in bob_html
    assert f'action="/comment/{c1_id}/delete"' not in bob_html

    # Bob edits comment 2
    bob_client.post(f"/comment/{c2_id}/edit", data={'comment': 'Bob comment edited'})
    assert db.comment.find_one({'_id': c1['_id']})['info'] == 'Alice comment'
    assert db.comment.find_one({'_id': c2['_id']})['info'] == 'Bob comment edited'

    # Alice deletes comment 1
    alice_client.post(f"/comment/{c1_id}/delete")
    assert db.comment.find_one({'_id': c1['_id']}) is None
    assert db.comment.find_one({'_id': c2['_id']}) is not None
    assert db.crackme.find_one({'hexid': hexid})['nbcomments'] == 1

    # Bob deletes comment 2
    bob_client.post(f"/comment/{c2_id}/delete")
    assert db.comment.find_one({'_id': c2['_id']}) is None
    assert db.crackme.find_one({'hexid': hexid})['nbcomments'] == 0


def test_comment_edit_sanitization_and_multiline(bob_client, client, db, sample_crackme, bob):
    hexid = sample_crackme['hexid']

    # Bob posts comment
    bob_client.post(f"/comment/{hexid}", data={'comment': 'Clean text'})
    c = db.comment.find_one({'author': 'bob', 'crackmehexid': hexid})
    cid = str(c['_id'])

    # Bob edits with HTML tags and newlines
    evil_payload = "<script>alert(1)</script><b>Safe bold</b>\nLine two\nLine three"
    bob_client.post(f"/comment/{cid}/edit", data={'comment': evil_payload})

    updated = db.comment.find_one({'_id': c['_id']})
    assert "<script>" not in updated['info']
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in updated['info'] or "alert(1)" in updated['info']
    assert "Line two\nLine three" in updated['info']

    # View page and verify sanitization and formatting
    html = client.get(f"/crackme/{hexid}").data.decode('utf-8')
    assert "<script>alert" not in html
    assert "(edited)" in html


def test_unauthenticated_requests_redirected(client, db, sample_crackme):
    hexid = sample_crackme['hexid']
    comment = comment_create('Test', 'alice', hexid)
    cid = str(comment['_id'])

    # Anonymous post to edit
    resp_edit = client.post(f"/comment/{cid}/edit", data={'comment': 'Hacked'})
    assert resp_edit.status_code == 302
    assert resp_edit.headers['Location'] == '/'
    assert db.comment.find_one({'_id': comment['_id']})['info'] == 'Test'

    # Anonymous post to delete
    resp_del = client.post(f"/comment/{cid}/delete")
    assert resp_del.status_code == 302
    assert resp_del.headers['Location'] == '/'
    assert db.comment.find_one({'_id': comment['_id']}) is not None

