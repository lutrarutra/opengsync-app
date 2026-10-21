"""Column value search (server/core/column_values.py, /htmx/column-values/<source>/search): values of free-text user
columns offered once per normalized key, in their most common spelling."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, categories as C

from ..db.create_units import create_user
from ._http import get
from ._profile import set_profile

URL = "/htmx/column-values/{source}/search"


def _url(source: str) -> str:
    return URL.format(source=source)


def _registration_token() -> str:
    from server.core import secrets
    return secrets.generate_registration_token(email="someone@example.com", role=C.UserRole.CLIENT)


def _users_with(session: SyncSession, *profiles: dict) -> None:
    for profile in profiles:
        set_profile(session, create_user(session), **{"institute": None, "department": None, "pi_name": None, "pi_email": None, **profile})
    session.commit()


def test_variants_collapse_into_most_common_spelling(client: TestClient, session: SyncSession, insider_token: str):
    _users_with(
        session,
        {"institute": "Medical University of Vienna"},
        {"institute": "Medical University of Vienna"},
        {"institute": "  medical   university OF vienna"},
        {"institute": "CeMM"},
    )

    body = get(client, _url("user_institute"), insider_token).json()

    assert [option["name"] for option in body["options"]] == ["Medical University of Vienna", "CeMM"]
    assert body["options"][0]["id"] == "medical university of vienna"
    assert body["has_more"] is False


def test_word_search_and_selected_id(client: TestClient, session: SyncSession, insider_token: str):
    _users_with(session, {"institute": "Medical University of Vienna"}, {"institute": "CeMM"})

    names = [o["name"] for o in get(client, _url("user_institute"), insider_token, params={"word": "cem"}).json()["options"]]
    assert names[0] == "CeMM"

    selected = get(client, _url("user_institute"), insider_token, params={"selected_id": "cemm"}).json()["options"]
    assert [o["name"] for o in selected] == ["CeMM"]


def test_departments_are_filtered_by_institute(client: TestClient, session: SyncSession, insider_token: str):
    _users_with(
        session,
        {"institute": "Medical University of Vienna", "department": "Department of Medicine I"},
        {"institute": "CeMM", "department": "Bioinformatics"},
    )

    def names(institute: str | None) -> list[str]:
        params = {"institute": institute} if institute is not None else {}
        return sorted(o["name"] for o in get(client, _url("user_department"), insider_token, params=params).json()["options"])

    assert names("medical university of VIENNA ") == ["Department of Medicine I"]
    assert names("A New Institute") == []
    assert names(None) == ["Bioinformatics", "Department of Medicine I"]


def test_paging(client: TestClient, session: SyncSession, insider_token: str):
    _users_with(session, *({"institute": f"Institute {i:02d}"} for i in range(25)))

    first = get(client, _url("user_institute"), insider_token).json()
    second = get(client, _url("user_institute"), insider_token, params={"page": 1}).json()

    assert len(first["options"]) == 20 and first["has_more"] is True
    assert len(second["options"]) == 5 and second["has_more"] is False


def test_pi_email_shown_to_insiders_only(
    client: TestClient, session: SyncSession, user, user_token: str, insider_token: str,
):
    _users_with(session, {"pi_name": "Grace Hopper", "pi_email": "grace@example.com"})

    insider_option = get(client, _url("user_pi"), insider_token).json()["options"][0]
    customer_option = get(client, _url("user_pi"), user_token).json()["options"][0]
    token_option = get(client, _url("user_pi"), params={"token": _registration_token()}).json()["options"][0]

    assert insider_option["description"] == "grace@example.com"
    for option in (customer_option, token_option):
        assert option == {"id": insider_option["id"], "name": "Grace Hopper"}
        assert "grace" not in option["id"]


def test_access_requires_login_or_token(client: TestClient):
    from server.core import secrets

    assert get(client, _url("user_institute")).status_code == 403
    assert get(client, _url("user_institute"), params={"token": "garbage"}).status_code == 403
    reset_token = secrets.create_password_reset_token(user_id=1)
    assert get(client, _url("user_institute"), params={"token": reset_token}).status_code == 403
    assert get(client, _url("user_institute"), params={"token": _registration_token()}).status_code == 200
    activation_token = secrets.create_activation_token(user_id=1)
    assert get(client, _url("user_institute"), params={"token": activation_token}).status_code == 200


def test_unknown_source_is_404(client: TestClient, insider_token: str):
    assert get(client, _url("lims_user_password"), insider_token).status_code == 404


def test_resolve_new_snaps_to_existing_values(session: SyncSession):
    from server.core import column_values

    _users_with(session, {"institute": "CeMM", "pi_name": "Grace Hopper", "pi_email": "grace@example.com"})
    sources = column_values.SOURCES

    assert column_values.resolve_new(session, sources["user_institute"], (" cemm ",)) == ("CeMM",)
    assert column_values.resolve_new(session, sources["user_institute"], ("New   Place ",)) == ("New Place",)
    assert column_values.resolve_new(session, sources["user_pi"], ("G. Hopper", "Grace@Example.com ")) == (
        "Grace Hopper", "grace@example.com",
    )
    assert column_values.resolve_new(session, sources["user_pi"], ("Ada", "ADA@example.com")) == ("Ada", "ada@example.com")
    assert column_values.lookup(session, sources["user_institute"], "unknown") is None
