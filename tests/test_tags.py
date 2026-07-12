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


def test_sublabels_are_valid_tags():
    # Specific techniques are part of the vocabulary too.
    assert is_valid_tag("UPX")
    assert is_valid_tag("IsDebuggerPresent")
    assert is_valid_tag("Control-flow flattening (CFF)")


def test_normalize_orders_sublabels_after_parent_class():
    raw = ["UPX", "Packer", "IsDebuggerPresent", "Anti-debugging"]
    # Each class comes before its own sub-labels; classes keep global order.
    assert normalize_tags(raw) == [
        "Anti-debugging", "IsDebuggerPresent", "Packer", "UPX"
    ]


def test_tag_groups_structure():
    from app.services.tags import get_tag_groups

    groups = {g["tag"]: g["sublabels"] for g in get_tag_groups()}
    assert "UPX" in groups["Packer"]
    assert "IsDebuggerPresent" in groups["Anti-debugging"]
    # A class without sub-labels has an empty list.
    assert groups["Nag / trial"] == []


def test_vocabulary_falls_back_to_default_when_db_empty(db):
    from app.services.tags import reload_vocabulary, get_classes, is_valid_tag

    reload_vocabulary()
    # No tag_vocabulary document -> built-in default applies.
    assert "Anti-debugging" in get_classes()
    assert is_valid_tag("UPX")


def test_vocabulary_is_read_from_db_and_overrides_default(db):
    from app.services import tags as T

    db.tag_vocabulary.replace_one(
        {"_id": T.VOCAB_ID},
        {
            "_id": T.VOCAB_ID,
            "classes": ["My Class", "Other Class"],
            "sublabels": {"My Class": ["Sub A", "Sub B"]},
            "field_parents": {"some_field": "My Class"},
            "qualify_suffix": {},
            "qualify_values": [],
            "dataset_url": "https://example.test/ds",
        },
        upsert=True,
    )
    T.reload_vocabulary()
    try:
        assert T.get_classes() == ["My Class", "Other Class"]
        assert T.is_valid_tag("Sub A")
        assert not T.is_valid_tag("UPX")  # default value no longer present
        # Canonical order: class then its sub-labels.
        assert T.normalize_tags(["Sub B", "My Class", "Sub A"]) == ["My Class", "Sub A", "Sub B"]
        assert T.get_dataset_url() == "https://example.test/ds"
        assert T.get_sublabel_fields() == {"some_field": "My Class"}
    finally:
        T.reload_vocabulary()


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


def test_search_by_sublabel(db, sample_crackme):
    from app.models.crackme import search_crackme

    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer", "UPX"]}}
    )
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439098"
    other["name"] = "FSG one"
    other["tags"] = ["Packer", "FSG"]
    db.crackme.insert_one(other)

    results, _ = search_crackme(tags=["UPX"])
    assert {c["name"] for c in results} == {"Test Crackme"}


# ---------------------------------------------------------------------------
# Submission + display
# ---------------------------------------------------------------------------

def test_upload_form_lists_classes_and_sublabels(alice_client):
    response = alice_client.get("/upload/crackme")
    assert response.status_code == 200
    assert b"Anti-debugging" in response.data
    assert b"String / data encryption" in response.data
    # Sub-labels are offered too.
    assert b"IsDebuggerPresent" in response.data
    assert b'value="UPX"' in response.data


def test_upload_stores_sublabel_tags(alice_client, db, monkeypatch):
    import app.controllers.crackme as cc
    monkeypatch.setattr(cc, "verify_recaptcha", lambda req: True)

    from io import BytesIO
    # A two-file zip passes the archive checks; content is irrelevant here.
    import zipfile
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    buf.seek(0)

    resp = alice_client.post("/upload/crackme", data={
        "name": "Tagged CM", "info": "info", "lang": "C/C++",
        "arch": "x86", "platform": "Windows", "difficulty": "3",
        "tags": ["Packer", "UPX", "not-real"],
        "file": (buf, "sample.zip"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200
    stored = db.crackme.find_one({"name": "Tagged CM"})
    assert stored is not None
    assert stored["tags"] == ["Packer", "UPX"]  # invalid dropped, ordered


def test_upload_allows_no_tags(alice_client, db, monkeypatch):
    # Tags are not mandatory: a crackme with no matching technique may have none.
    import app.controllers.crackme as cc
    monkeypatch.setattr(cc, "verify_recaptcha", lambda req: True)

    from io import BytesIO
    import zipfile
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    buf.seek(0)

    resp = alice_client.post("/upload/crackme", data={
        "name": "No Tag CM", "info": "info", "lang": "C/C++",
        "arch": "x86", "platform": "Windows", "difficulty": "3",
        # no tags
        "file": (buf, "sample.zip"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200
    stored = db.crackme.find_one({"name": "No Tag CM"})
    assert stored is not None
    assert stored["tags"] == []


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
    # Bare search page uses a bookmarkable GET form.
    assert b'method="get" action="/search"' in response.data


def test_bare_search_get_shows_no_results(client, db, sample_crackme):
    # No query params -> empty form, no result rows.
    response = client.get("/search")
    assert response.status_code == 200
    assert b"Test Crackme" not in response.data


def test_search_by_tag_via_get_is_bookmarkable(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer", "UPX"]}}
    )
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439097"
    other["name"] = "No Tags CM"
    other["tags"] = []
    db.crackme.insert_one(other)

    # A plain GET URL (what a tag chip links to / a bookmark) runs the search.
    response = client.get("/search?tags=UPX")
    assert response.status_code == 200
    assert b"Test Crackme" in response.data
    assert b"No Tags CM" not in response.data
    # The tag stays selected so the URL round-trips in the form.
    assert b'value="UPX" selected' in response.data


def test_crackme_tag_chip_links_to_get_search(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["String / data encryption"]}}
    )
    response = client.get(f"/crackme/{sample_crackme['hexid']}")
    assert response.status_code == 200
    # Chip is a GET link with the tag properly URL-encoded.
    assert b'href="/search?tags=String%20/%20data%20encryption"' in response.data


# ---------------------------------------------------------------------------
# Tag change requests (user side)
# ---------------------------------------------------------------------------

def test_request_tag_change_diffs_applied_set(alice_client, db, sample_crackme):
    # Crackme currently has Anti-debugging; user wants Packer applied instead.
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Anti-debugging"]}}
    )
    response = alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"applied": ["Packer"], "note": "uses UPX"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    req = db.tag_request.find_one({"crackme_hexid": sample_crackme["hexid"]})
    assert req is not None
    assert req["add"] == ["Packer"]        # in desired, not in current
    assert req["remove"] == ["Anti-debugging"]  # in current, not in desired
    assert req["status"] == "pending"
    assert req["requester"] == "alice"


def test_request_tag_change_no_change_creates_nothing(alice_client, db, sample_crackme):
    # Desired set equals current set -> no request.
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"tags": ["Packer"]}}
    )
    alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"applied": ["Packer"], "note": "no change"},
    )
    assert db.tag_request.count_documents({}) == 0


def test_request_tag_change_requires_login(client, sample_crackme):
    response = client.post(
        f"/crackme/{sample_crackme['hexid']}/tags/request",
        data={"applied": ["Packer"]},
    )
    # login_required redirects anonymous users.
    assert response.status_code in (301, 302)


def test_duplicate_pending_request_blocked(alice_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    alice_client.post(f"/crackme/{hexid}/tags/request", data={"applied": ["Packer"]})
    alice_client.post(f"/crackme/{hexid}/tags/request", data={"applied": ["Anti-debugging"]})
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
    # The edit page uses the transfer widget seeded with the current tags.
    assert b'id="edit-tag-transfer"' in page.data
    assert b'"Anti-debugging"' in page.data

    saved = client.post("/review/editcrackme", data={
        "crackme_uuid": hexid,
        "info": sample_crackme["info"], "lang": sample_crackme["lang"],
        "arch": sample_crackme["arch"], "platform": sample_crackme["platform"],
        "tags": ["Packer", "bogus"], "csrf_token": "admin-csrf",
    })
    assert saved.status_code == 200
    # Invalid tag dropped; valid one persisted.
    assert db.crackme.find_one({"hexid": hexid})["tags"] == ["Packer"]
