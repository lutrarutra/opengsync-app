"""Admin Affiliations page (server/core/affiliation_values.py): institutes, departments and PIs of users listed once
per normalized key, edited and merged for all users having them."""
import hashlib

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, models

from ..db.create_units import create_user
from ._http import assert_form_invalid, assert_htmx_redirect, get, post_form
from ._profile import set_profile

MUW = "Medical University of Vienna"
CEMM = "CeMM"


def _pi_key(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode()).hexdigest()


def _users(session: SyncSession, *profiles: dict) -> list[models.User]:
    users = [
        set_profile(session, create_user(session), **{"institute": None, "department": None, "pi_name": None, "pi_email": None, **profile})
        for profile in profiles
    ]
    session.commit()
    return users


def _table(client: TestClient, token: str, kind: str, **params):
    return get(client, "/htmx/admin/affiliations", token, htmx=True, params={"kind": kind, **params})


def _edit(client: TestClient, token: str, kind: str, params: dict, **data):
    return post_form(client, f"/htmx/admin/affiliations/{kind}/edit", data, token, params=params, htmx=True)


def _merge(client: TestClient, token: str, kind: str, params: dict, target: str):
    return post_form(client, f"/htmx/admin/affiliations/{kind}/merge", {"target": target, "target-text": ""}, token, params=params, htmx=True)


def test_admin_only(client: TestClient, admin_token: str, insider_token: str):
    assert get(client, "/admin/affiliations", admin_token).status_code == 200
    assert get(client, "/admin/affiliations", insider_token).status_code in (302, 303, 403)
    assert _table(client, insider_token, "institute").status_code == 403
    assert _edit(client, insider_token, "institute", {"key": "cemm"}, name="X").status_code == 403
    assert _table(client, admin_token, "unknown").status_code == 422


def test_values_listed_once_with_counts_and_spellings(client: TestClient, session: SyncSession, admin_token: str):
    _users(session, {"institute": MUW}, {"institute": MUW}, {"institute": "  medical   university OF vienna"}, {"institute": CEMM})

    html = _table(client, admin_token, "institute").text
    assert html.index(MUW) < html.index(CEMM)  # most users first
    assert "medical   university OF vienna" not in html
    assert "2 spellings" in html

    by_name = _table(client, admin_token, "institute", order_by="name:asc").text
    assert by_name.index(CEMM) < by_name.index(MUW)

    searched = _table(client, admin_token, "institute", name="cem").text
    assert CEMM in searched and MUW not in searched

    assert _table(client, admin_token, "institute", order_by="email:asc").status_code == 400


def test_departments_are_scoped_to_their_institute(client: TestClient, session: SyncSession, admin_token: str):
    _users(session, {"institute": MUW, "department": "Bioinformatics"}, {"institute": CEMM, "department": "Bioinformatics"})

    html = _table(client, admin_token, "department").text
    assert html.count("Bioinformatics") >= 2
    assert MUW in html and CEMM in html


def test_pi_with_account_is_linked(client: TestClient, session: SyncSession, admin_token: str):
    pi = create_user(session)
    _users(session, {"pi_name": "Grace Hopper", "pi_email": pi.email.upper()}, {"pi_name": "Ada Lovelace", "pi_email": "ada@example.com"})

    html = _table(client, admin_token, "pi").text
    assert f"/users/{pi.id}" in html
    assert "ada@example.com" in html


def test_edit_renames_every_spelling(client: TestClient, session: SyncSession, admin_token: str):
    a, b, other = _users(session, {"institute": MUW}, {"institute": " medical university of VIENNA"}, {"institute": CEMM})

    assert "Used by 2 users" in get(client, "/htmx/admin/affiliations/institute/edit", admin_token, htmx=True, params={"key": "medical university of vienna"}).text

    response = _edit(client, admin_token, "institute", {"key": "medical university of vienna"}, name="  MedUni   Wien ")
    assert_htmx_redirect(response, "/admin/affiliations?tab=affiliations-institute")

    session.expire_all()
    assert [session.get(models.User, u.id).institute for u in (a, b, other)] == ["MedUni Wien", "MedUni Wien", CEMM]


def test_edit_department_only_at_its_institute(client: TestClient, session: SyncSession, admin_token: str):
    at_muw, at_cemm = _users(session, {"institute": MUW, "department": "Bioinf"}, {"institute": CEMM, "department": "Bioinf"})

    response = _edit(client, admin_token, "department", {"key": "bioinf", "institute": "medical university of vienna"}, name="Bioinformatics")
    assert_htmx_redirect(response)

    session.expire_all()
    assert session.get(models.User, at_muw.id).department == "Bioinformatics"
    assert session.get(models.User, at_cemm.id).department == "Bioinf"


def test_edit_onto_existing_value_asks_to_merge(client: TestClient, session: SyncSession, admin_token: str):
    user, = _users(session, {"institute": MUW}, {"institute": CEMM})[:1]

    assert_form_invalid(_edit(client, admin_token, "institute", {"key": "medical university of vienna"}, name="cemm"), "merge into it instead")
    assert_form_invalid(_edit(client, admin_token, "institute", {"key": "medical university of vienna"}, name="X"), "at least 2")

    session.expire_all()
    assert session.get(models.User, user.id).institute == MUW


def test_edit_pi_name_and_email(client: TestClient, session: SyncSession, admin_token: str):
    a, b = _users(session, {"pi_name": "G. Hopper", "pi_email": "grace@example.com"}, {"pi_name": "Grace Hopper", "pi_email": "Grace@Example.com"})

    response = _edit(client, admin_token, "pi", {"key": _pi_key("grace@example.com")}, name="Grace Hopper", email=" Grace.Hopper@Example.com ")
    assert_htmx_redirect(response)

    session.expire_all()
    for user in (a, b):
        user = session.get(models.User, user.id)
        assert (user.pi_name, user.pi_email) == ("Grace Hopper", "grace.hopper@example.com")


def test_edit_pi_email_of_an_account_is_refused(client: TestClient, session: SyncSession, admin_token: str):
    pi = create_user(session)
    student, = _users(session, {"pi_name": "The PI", "pi_email": pi.email})

    params = {"key": _pi_key(pi.email)}
    assert_form_invalid(_edit(client, admin_token, "pi", params, name="The PI", email="other@example.com"), "change the email of their account")
    # the name can still be fixed
    assert_htmx_redirect(_edit(client, admin_token, "pi", params, name="Dr. The PI", email=pi.email))

    session.expire_all()
    student = session.get(models.User, student.id)
    assert (student.pi_name, student.pi_email) == ("Dr. The PI", pi.email.lower())


def test_merge_institutes_keeps_departments(client: TestClient, session: SyncSession, admin_token: str):
    src, dst = _users(session, {"institute": "Med Uni Vienna", "department": "Bioinf"}, {"institute": MUW, "department": "Genomics"})

    page = get(client, "/htmx/admin/affiliations/institute/merge", admin_token, htmx=True, params={"key": "med uni vienna"})
    assert page.status_code == 200 and "Used by 1 user" in page.text

    assert_htmx_redirect(_merge(client, admin_token, "institute", {"key": "med uni vienna"}, "medical university of vienna"))

    session.expire_all()
    src, dst = session.get(models.User, src.id), session.get(models.User, dst.id)
    assert (src.institute, src.department) == (MUW, "Bioinf")
    assert dst.institute == MUW


def test_merge_validation(client: TestClient, session: SyncSession, admin_token: str):
    _users(session, {"institute": MUW, "department": "Bioinf"}, {"institute": CEMM, "department": "Genomics"})
    params = {"key": "bioinf", "institute": "medical university of vienna"}

    assert_form_invalid(_merge(client, admin_token, "department", params, ""), "Merge Into Department is required")
    assert_form_invalid(_merge(client, admin_token, "department", params, "bioinf"), "Select another department")
    # a department of another institute
    assert_form_invalid(_merge(client, admin_token, "department", params, "genomics"), "Invalid department")
    assert_form_invalid(_merge(client, admin_token, "department", params, "new"), "Select an existing")
    assert get(client, "/htmx/admin/affiliations/department/merge", admin_token, htmx=True, params={"key": "nope"}).status_code == 404


def test_merge_pis(client: TestClient, session: SyncSession, admin_token: str):
    src, dst = _users(session, {"pi_name": "G Hopper", "pi_email": "g.hopper@example.com"}, {"pi_name": "Grace Hopper", "pi_email": "grace@example.com"})

    assert_htmx_redirect(_merge(client, admin_token, "pi", {"key": _pi_key("g.hopper@example.com")}, _pi_key("grace@example.com")))

    session.expire_all()
    src = session.get(models.User, src.id)
    assert (src.pi_name, src.pi_email) == ("Grace Hopper", "grace@example.com")


def test_merge_away_pi_with_account_is_refused(client: TestClient, session: SyncSession, admin_token: str):
    pi = create_user(session)
    _users(session, {"pi_name": "The PI", "pi_email": pi.email}, {"pi_name": "Typo PI", "pi_email": "typo@example.com"})

    assert_form_invalid(_merge(client, admin_token, "pi", {"key": _pi_key(pi.email)}, _pi_key("typo@example.com")), "merge the other PI into this one")
    assert_htmx_redirect(_merge(client, admin_token, "pi", {"key": _pi_key("typo@example.com")}, _pi_key(pi.email)))
