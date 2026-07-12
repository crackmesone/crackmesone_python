"""Tests for crackme obfuscation tags: vocabulary, submission, search,
display, reviewer overrides, and the tag change request workflow."""

from app.services.tags import normalize_tags, is_valid_tag


# ---------------------------------------------------------------------------
# Vocabulary / normalization
# ---------------------------------------------------------------------------

def test_normalize_tags_filters_dedupes_and_orders():
    raw = ["Packer", "not-a-real-tag", "Anti-debugging", "Packer", "  Anti-debugging  "]
    result = normalize_tags(raw)
    # Only valid tags survive, deduped, in canonical order (Anti-debugging first).
    assert result == ["Anti-debugging", "Packer"]


def test_normalize_tags_handles_empty_and_none():
    assert normalize_tags([]) == []
    assert normalize_tags(None) == []
    assert normalize_tags(["totally", "invalid"]) == []


def test_is_valid_tag():
    assert is_valid_tag("Anti-debugging")
    assert not is_valid_tag("Anti-debugging ")
    assert not is_valid_tag("nonsense")


# ---------------------------------------------------------------------------
# Model layer
# ---------------------------------------------------------------------------

def test_crackme_create_prepare_stores_tags():
    from app.models.crackme import crackme_create_prepare

    crackme = crackme_create_prepare(
        "n", "i", "alice", "C/C++", "x86", "Windows", 10, "n.exe",
        tags=["Packer", "Anti-debugging"]
    )
    assert crackme["tags"] == ["Packer", "Anti-debugging"]


def test_crackme_create_prepare_defaults_empty_tags():
    from app.models.crackme import crackme_create_prepare

    crackme = crackme_create_prepare(
        "n", "i", "alice", "C/C++", "x86", "Windows", 10, "n.exe"
    )
    assert crackme["tags"] == []


def test_crackme_set_tags_returns_old_and_writes_new(db, sample_crackme):
    from app.models.crackme import crackme_set_tags

    old = crackme_set_tags(sample_crackme["hexid"], ["Packer"])
    assert old == []
    stored = db.crackme.find_one({"hexid": sample_crackme["hexid"]})
    assert stored["tags"] == ["Packer"]


def test_crackme_set_tags_missing_returns_none(db):
    from app.models.crackme import crackme_set_tags

    assert crackme_set_tags("deadbeefdeadbeefdeadbeef", ["Packer"]) is None


def test_search_by_tags_requires_all(db, sample_crackme):
    from app.models.crackme import search_crackme

    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer", "Anti-debugging"]}}
    )
    # Second crackme with only one of the tags.
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439099"
    other["name"] = "Only Packer"
    other["tags"] = ["Packer"]
    db.crackme.insert_one(other)

    results, _ = search_crackme(tags=["Packer", "Anti-debugging"])
    names = {c["name"] for c in results}
    assert names == {"Test Crackme"}

    results, _ = search_crackme(tags=["Packer"])
    names = {c["name"] for c in results}
    assert names == {"Test Crackme", "Only Packer"}


# ---------------------------------------------------------------------------
# Submission + display
# ---------------------------------------------------------------------------

def test_upload_form_lists_all_tags(alice_client):
    response = alice_client.get("/upload/crackme")
    assert response.status_code == 200
    assert b"Anti-debugging" in response.data
    assert b"String / data encryption" in response.data


def test_crackme_view_shows_tags_and_help(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer"]}}
    )
    response = client.get(f"/crackme/{sample_crackme['hexid']}")
    assert response.status_code == 200
    assert b"Packer" in response.data
    # The "?" help link points at the dataset.
    assert b"crackmes-re-dataset" in response.data


def test_search_page_offers_tag_filter(client):
    response = client.get("/search")
    assert response.status_code == 200
    assert b'name="tags"' in response.data


# ---------------------------------------------------------------------------
# Tag change requests (user side)
# ---------------------------------------------------------------------------

def test_request_tag_change_creates_pending(alice_client, db, sample_crackme):
    response = alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"add": ["Packer"], "note": "uses UPX"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    req = db.tag_request.find_one({"crackme_hexid": sample_crackme["hexid"]})
    assert req is not None
    assert req["add"] == ["Packer"]
    assert req["status"] == "pending"
    assert req["requester"] == "alice"


def test_request_tag_change_rejects_empty(alice_client, db, sample_crackme):
    alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"note": "nothing"},
    )
    assert db.tag_request.count_documents({}) == 0


def test_request_tag_change_ignores_noop_add(alice_client, db, sample_crackme):
    # Tag already applied -> add is a no-op and should not create a request.
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer"]}}
    )
    alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"add": ["Packer"]},
    )
    assert db.tag_request.count_documents({}) == 0


def test_request_tag_change_requires_login(client, sample_crackme):
    response = client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"add": ["Packer"]},
    )
    # login_required redirects anonymous users.
    assert response.status_code in (301, 302)


def test_duplicate_pending_request_blocked(alice_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    alice_client.post(f"/crackme/{hexid}/tags/request", data={"add": ["Packer"]})
    alice_client.post(f"/crackme/{hexid}/tags/request", data={"add": ["Anti-debugging"]})
    assert db.tag_request.count_documents({"crackme_hexid": hexid}) == 1


# ---------------------------------------------------------------------------
# Reviewer side
# ---------------------------------------------------------------------------

def test_reviewer_settags_overrides(reviewer_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    response = reviewer_client.post(
        "/review/settags",
        data={"uuid": hexid, "tags": ["Packer", "Anti-debugging"], "redirect_to": "view", "csrf_token": "test-csrf-token"},
    )
    assert response.status_code == 302
    stored = db.crackme.find_one({"hexid": hexid})
    assert sorted(stored["tags"]) == ["Anti-debugging", "Packer"]


def test_reviewer_settags_drops_invalid(reviewer_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    reviewer_client.post(
        "/review/settags",
        data={"uuid": hexid, "tags": ["Packer", "bogus-tag"], "csrf_token": "test-csrf-token"},
    )
    stored = db.crackme.find_one({"hexid": hexid})
    assert stored["tags"] == ["Packer"]


def test_reviewer_approve_tag_request_applies_and_notifies(reviewer_client, db, sample_crackme, alice):
    from app.models.tag_request import tag_request_create

    hexid = sample_crackme["hexid"]
    db.crackme.update_one({"hexid": hexid}, {"$set": {"tags": ["Anti-debugging"]}})
    req = tag_request_create(hexid, sample_crackme["name"], "alice",
                             add=["Packer"], remove=["Anti-debugging"])

    response = reviewer_client.post(
        "/review/approvetagrequest", data={"uuid": req["hexid"], "csrf_token": "test-csrf-token"}
    )
    assert response.status_code == 302

    stored = db.crackme.find_one({"hexid": hexid})
    assert stored["tags"] == ["Packer"]

    updated_req = db.tag_request.find_one({"hexid": req["hexid"]})
    assert updated_req["status"] == "approved"
    assert updated_req["reviewed_by"] == "reviewer"
    # Requester was notified.
    assert db.notifications.count_documents({"user": "alice"}) == 1


def test_reviewer_reject_tag_request(reviewer_client, db, sample_crackme, alice):
    from app.models.tag_request import tag_request_create

    hexid = sample_crackme["hexid"]
    req = tag_request_create(hexid, sample_crackme["name"], "alice", add=["Packer"])

    response = reviewer_client.post(
        "/review/rejecttagrequest",
        data={"uuid": req["hexid"], "reject_reason": "not accurate", "csrf_token": "test-csrf-token"},
    )
    assert response.status_code == 302

    # Crackme tags unchanged; request marked rejected.
    stored = db.crackme.find_one({"hexid": hexid})
    assert stored.get("tags", []) == []
    updated_req = db.tag_request.find_one({"hexid": req["hexid"]})
    assert updated_req["status"] == "rejected"


def test_tagrequests_page_lists_pending(reviewer_client, db, sample_crackme):
    from app.models.tag_request import tag_request_create

    tag_request_create(sample_crackme["hexid"], sample_crackme["name"], "alice",
                       add=["Packer"], note="uses upx")
    response = reviewer_client.get("/review/tagrequests")
    assert response.status_code == 200
    assert b"Packer" in response.data
    assert b"alice" in response.data


def test_dashboard_shows_tag_request_count(reviewer_client, db, sample_crackme):
    from app.models.tag_request import tag_request_create

    tag_request_create(sample_crackme["hexid"], sample_crackme["name"], "alice", add=["Packer"])
    response = reviewer_client.get("/review/dashboard")
    assert response.status_code == 200
    assert b"tag change requests" in response.data


def _admin_client(app):
    from review import routes

    routes.users["admin"] = {
        "password_hash": routes.hash_string("admin-passwordtest-reviewer-salt"),
        "is_admin": True,
    }
    client = app.test_client()
    with client.session_transaction() as session:
        session["_reviewer_user"] = "admin"
        session["_reviewer_is_admin"] = True
        session["_reviewer_csrf_token"] = "admin-csrf"
    return client


def test_admin_editcrackme_shows_and_saves_tags(app, db, sample_crackme):
    client = _admin_client(app)
    hexid = sample_crackme["hexid"]
    db.crackme.update_one({"hexid": hexid}, {"$set": {"tags": ["Anti-debugging"]}})

    page = client.get(f"/review/editcrackme?crackme_uuid={hexid}")
    assert page.status_code == 200
    assert b'value="Anti-debugging" checked' in page.data

    saved = client.post("/review/editcrackme", data={
        "crackme_uuid": hexid,
        "info": sample_crackme["info"], "lang": sample_crackme["lang"],
        "arch": sample_crackme["arch"], "platform": sample_crackme["platform"],
        "tags": ["Packer", "bogus"], "csrf_token": "admin-csrf",
    })
    assert saved.status_code == 200
    # Invalid tag dropped; valid one persisted.
    assert db.crackme.find_one({"hexid": hexid})["tags"] == ["Packer"]
