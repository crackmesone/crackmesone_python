"""Tests for crackme obfuscation labels: vocabulary, submission, search,
display, reviewer overrides, and the label change request workflow."""

from app.services.labels import normalize_labels, is_valid_label


# ---------------------------------------------------------------------------
# Vocabulary / normalization
# ---------------------------------------------------------------------------

def test_normalize_labels_filters_dedupes_and_orders():
    raw = ["Packer", "not-a-real-label", "Anti-debugging", "Packer", "  Anti-debugging  "]
    result = normalize_labels(raw)
    # Only valid labels survive, deduped, in canonical order (Anti-debugging first).
    assert result == ["Anti-debugging", "Packer"]


def test_normalize_labels_handles_empty_and_none():
    assert normalize_labels([]) == []
    assert normalize_labels(None) == []
    assert normalize_labels(["totally", "invalid"]) == []


def test_is_valid_label():
    assert is_valid_label("Anti-debugging")
    assert not is_valid_label("Anti-debugging ")
    assert not is_valid_label("nonsense")


def test_sublabels_are_valid_labels():
    # Specific techniques are part of the vocabulary too.
    assert is_valid_label("UPX")
    assert is_valid_label("IsDebuggerPresent")
    assert is_valid_label("Control-flow flattening (CFF)")


def test_normalize_orders_sublabels_after_parent_class():
    raw = ["UPX", "Packer", "IsDebuggerPresent", "Anti-debugging"]
    # Each class comes before its own sub-labels; classes keep global order.
    assert normalize_labels(raw) == [
        "Anti-debugging", "IsDebuggerPresent", "Packer", "UPX"
    ]


def test_label_groups_structure():
    from app.services.labels import get_label_groups

    groups = {g["label"]: g["sublabels"] for g in get_label_groups()}
    assert "UPX" in groups["Packer"]
    assert "IsDebuggerPresent" in groups["Anti-debugging"]
    # A class without sub-labels has an empty list.
    assert groups["Nag / trial"] == []


def test_vocabulary_falls_back_to_default_when_db_empty(db):
    from app.services.labels import reload_vocabulary, get_classes, is_valid_label

    reload_vocabulary()
    # No label_vocabulary document -> built-in default applies.
    assert "Anti-debugging" in get_classes()
    assert is_valid_label("UPX")


def test_vocabulary_is_read_from_db_and_overrides_default(db):
    from app.services import labels as T

    db.label_vocabulary.replace_one(
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
        assert T.is_valid_label("Sub A")
        assert not T.is_valid_label("UPX")  # default value no longer present
        # Canonical order: class then its sub-labels.
        assert T.normalize_labels(["Sub B", "My Class", "Sub A"]) == ["My Class", "Sub A", "Sub B"]
        assert T.get_dataset_url() == "https://example.test/ds"
        assert T.get_sublabel_fields() == {"some_field": "My Class"}
    finally:
        T.reload_vocabulary()


# ---------------------------------------------------------------------------
# Model layer
# ---------------------------------------------------------------------------

def test_crackme_create_prepare_stores_labels():
    from app.models.crackme import crackme_create_prepare

    crackme = crackme_create_prepare(
        "n", "i", "alice", "C/C++", "x86", "Windows", 10, "n.exe",
        labels=["Packer", "Anti-debugging"]
    )
    assert crackme["labels"] == ["Packer", "Anti-debugging"]


def test_crackme_create_prepare_defaults_empty_labels():
    from app.models.crackme import crackme_create_prepare

    crackme = crackme_create_prepare(
        "n", "i", "alice", "C/C++", "x86", "Windows", 10, "n.exe"
    )
    assert crackme["labels"] == []


def test_crackme_set_labels_returns_old_and_writes_new(db, sample_crackme):
    from app.models.crackme import crackme_set_labels

    old = crackme_set_labels(sample_crackme["hexid"], ["Packer"])
    assert old == []
    stored = db.crackme.find_one({"hexid": sample_crackme["hexid"]})
    assert stored["labels"] == ["Packer"]


def test_crackme_set_labels_missing_returns_none(db):
    from app.models.crackme import crackme_set_labels

    assert crackme_set_labels("deadbeefdeadbeefdeadbeef", ["Packer"]) is None


def test_search_by_labels_requires_all(db, sample_crackme):
    from app.models.crackme import search_crackme

    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Packer", "Anti-debugging"]}}
    )
    # Second crackme with only one of the labels.
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439099"
    other["name"] = "Only Packer"
    other["labels"] = ["Packer"]
    db.crackme.insert_one(other)

    results, _ = search_crackme(labels=["Packer", "Anti-debugging"])
    names = {c["name"] for c in results}
    assert names == {"Test Crackme"}

    results, _ = search_crackme(labels=["Packer"])
    names = {c["name"] for c in results}
    assert names == {"Test Crackme", "Only Packer"}


def test_search_by_sublabel(db, sample_crackme):
    from app.models.crackme import search_crackme

    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Packer", "UPX"]}}
    )
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439098"
    other["name"] = "FSG one"
    other["labels"] = ["Packer", "FSG"]
    db.crackme.insert_one(other)

    results, _ = search_crackme(labels=["UPX"])
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


def test_upload_stores_sublabel_labels(alice_client, db, monkeypatch):
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
        "name": "Labeled CM", "info": "info", "lang": "C/C++",
        "arch": "x86", "platform": "Windows", "difficulty": "3",
        "labels": ["Packer", "UPX", "not-real"],
        "file": (buf, "sample.zip"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200
    stored = db.crackme.find_one({"name": "Labeled CM"})
    assert stored is not None
    assert stored["labels"] == ["Packer", "UPX"]  # invalid dropped, ordered


def test_upload_allows_no_labels(alice_client, db, monkeypatch):
    # Labels are not mandatory: a crackme with no matching technique may have none.
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
        "name": "No Label CM", "info": "info", "lang": "C/C++",
        "arch": "x86", "platform": "Windows", "difficulty": "3",
        # no labels
        "file": (buf, "sample.zip"),
    }, content_type="multipart/form-data")
    assert resp.status_code == 200
    stored = db.crackme.find_one({"name": "No Label CM"})
    assert stored is not None
    assert stored["labels"] == []


def test_crackme_view_shows_labels_and_help(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Packer"]}}
    )
    response = client.get(f"/crackme/{sample_crackme['hexid']}")
    assert response.status_code == 200
    assert b"Packer" in response.data
    # The "?" help link points at the dataset.
    assert b"crackmes-re-dataset" in response.data


def test_search_page_offers_label_filter(client):
    response = client.get("/search")
    assert response.status_code == 200
    assert b'name="labels"' in response.data
    # Bare search page uses a bookmarkable GET form.
    assert b'method="get" action="/search"' in response.data


def test_bare_search_get_shows_no_results(client, db, sample_crackme):
    # No query params -> empty form, no result rows.
    response = client.get("/search")
    assert response.status_code == 200
    assert b"Test Crackme" not in response.data


def test_search_by_label_via_get_is_bookmarkable(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Packer", "UPX"]}}
    )
    other = dict(sample_crackme)
    other.pop("_id")
    other["hexid"] = "507f1f77bcf86cd799439097"
    other["name"] = "No Labels CM"
    other["labels"] = []
    db.crackme.insert_one(other)

    # A plain GET URL (what a label chip links to / a bookmark) runs the search.
    response = client.get("/search?labels=UPX")
    assert response.status_code == 200
    assert b"Test Crackme" in response.data
    assert b"No Labels CM" not in response.data
    # The label stays checked so the URL round-trips in the form.
    assert b'value="UPX" data-label-parent="Packer" checked' in response.data


def test_crackme_label_chip_links_to_get_search(client, db, sample_crackme):
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["String / data encryption"]}}
    )
    response = client.get(f"/crackme/{sample_crackme['hexid']}")
    assert response.status_code == 200
    # Chip is a GET link with the label properly URL-encoded.
    assert b'href="/search?labels=String%20/%20data%20encryption"' in response.data


# ---------------------------------------------------------------------------
# Label change requests (user side)
# ---------------------------------------------------------------------------

def test_request_label_change_diffs_applied_set(alice_client, db, sample_crackme):
    # Crackme currently has Anti-debugging; user wants Packer applied instead.
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Anti-debugging"]}}
    )
    response = alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/labels/request",
        data={"applied": ["Packer"], "note": "uses UPX"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    req = db.label_request.find_one({"crackme_hexid": sample_crackme["hexid"]})
    assert req is not None
    assert req["add"] == ["Packer"]        # in desired, not in current
    assert req["remove"] == ["Anti-debugging"]  # in current, not in desired
    assert req["status"] == "pending"
    assert req["requester"] == "alice"


def test_request_label_change_no_change_creates_nothing(alice_client, db, sample_crackme):
    # Desired set equals current set -> no request.
    db.crackme.update_one(
        {"hexid": sample_crackme["hexid"]},
        {"$set": {"labels": ["Packer"]}}
    )
    alice_client.post(
        f"/crackme/{sample_crackme['hexid']}/labels/request",
        data={"applied": ["Packer"], "note": "no change"},
    )
    assert db.label_request.count_documents({}) == 0


def test_request_label_change_requires_login(client, sample_crackme):
    response = client.post(
        f"/crackme/{sample_crackme['hexid']}/labels/request",
        data={"applied": ["Packer"]},
    )
    # login_required redirects anonymous users.
    assert response.status_code in (301, 302)


def test_duplicate_pending_request_blocked(alice_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    alice_client.post(f"/crackme/{hexid}/labels/request", data={"applied": ["Packer"]})
    alice_client.post(f"/crackme/{hexid}/labels/request", data={"applied": ["Anti-debugging"]})
    assert db.label_request.count_documents({"crackme_hexid": hexid}) == 1


# ---------------------------------------------------------------------------
# Reviewer side
# ---------------------------------------------------------------------------

def test_reviewer_setlabels_overrides(reviewer_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    response = reviewer_client.post(
        "/review/setlabels",
        data={"uuid": hexid, "labels": ["Packer", "Anti-debugging"], "redirect_to": "view", "csrf_token": "test-csrf-token"},
    )
    assert response.status_code == 302
    stored = db.crackme.find_one({"hexid": hexid})
    assert sorted(stored["labels"]) == ["Anti-debugging", "Packer"]


def test_reviewer_setlabels_drops_invalid(reviewer_client, db, sample_crackme):
    hexid = sample_crackme["hexid"]
    reviewer_client.post(
        "/review/setlabels",
        data={"uuid": hexid, "labels": ["Packer", "bogus-label"], "csrf_token": "test-csrf-token"},
    )
    stored = db.crackme.find_one({"hexid": hexid})
    assert stored["labels"] == ["Packer"]


def test_reviewer_approve_label_request_applies_and_notifies(reviewer_client, db, sample_crackme, alice):
    from app.models.label_request import label_request_create

    hexid = sample_crackme["hexid"]
    db.crackme.update_one({"hexid": hexid}, {"$set": {"labels": ["Anti-debugging"]}})
    req = label_request_create(hexid, sample_crackme["name"], "alice",
                             add=["Packer"], remove=["Anti-debugging"])

    response = reviewer_client.post(
        "/review/approvelabelrequest", data={"uuid": req["hexid"], "csrf_token": "test-csrf-token"}
    )
    assert response.status_code == 302

    stored = db.crackme.find_one({"hexid": hexid})
    assert stored["labels"] == ["Packer"]

    updated_req = db.label_request.find_one({"hexid": req["hexid"]})
    assert updated_req["status"] == "approved"
    assert updated_req["reviewed_by"] == "reviewer"
    # Requester was notified.
    assert db.notifications.count_documents({"user": "alice"}) == 1


def test_reviewer_reject_label_request(reviewer_client, db, sample_crackme, alice):
    from app.models.label_request import label_request_create

    hexid = sample_crackme["hexid"]
    req = label_request_create(hexid, sample_crackme["name"], "alice", add=["Packer"])

    response = reviewer_client.post(
        "/review/rejectlabelrequest",
        data={"uuid": req["hexid"], "reject_reason": "not accurate", "csrf_token": "test-csrf-token"},
    )
    assert response.status_code == 302

    # Crackme labels unchanged; request marked rejected.
    stored = db.crackme.find_one({"hexid": hexid})
    assert stored.get("labels", []) == []
    updated_req = db.label_request.find_one({"hexid": req["hexid"]})
    assert updated_req["status"] == "rejected"


def test_labelrequests_page_lists_pending(reviewer_client, db, sample_crackme):
    from app.models.label_request import label_request_create

    label_request_create(sample_crackme["hexid"], sample_crackme["name"], "alice",
                       add=["Packer"], note="uses upx")
    response = reviewer_client.get("/review/labelrequests")
    assert response.status_code == 200
    assert b"Packer" in response.data
    assert b"alice" in response.data


def test_dashboard_shows_label_request_count(reviewer_client, db, sample_crackme):
    from app.models.label_request import label_request_create

    label_request_create(sample_crackme["hexid"], sample_crackme["name"], "alice", add=["Packer"])
    response = reviewer_client.get("/review/dashboard")
    assert response.status_code == 200
    assert b"label change requests" in response.data


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


def test_admin_editcrackme_shows_and_saves_labels(app, db, sample_crackme):
    client = _admin_client(app)
    hexid = sample_crackme["hexid"]
    db.crackme.update_one({"hexid": hexid}, {"$set": {"labels": ["Anti-debugging"]}})

    page = client.get(f"/review/editcrackme?crackme_uuid={hexid}")
    assert page.status_code == 200
    # The edit page uses the grouped label checkboxes seeded with the current labels.
    assert b'value="Anti-debugging" data-label-class="1" checked' in page.data

    saved = client.post("/review/editcrackme", data={
        "crackme_uuid": hexid,
        "info": sample_crackme["info"], "lang": sample_crackme["lang"],
        "arch": sample_crackme["arch"], "platform": sample_crackme["platform"],
        "labels": ["Packer", "bogus"], "csrf_token": "admin-csrf",
    })
    assert saved.status_code == 200
    # Invalid label dropped; valid one persisted.
    assert db.crackme.find_one({"hexid": hexid})["labels"] == ["Packer"]
