"""CompleteRegistrationForm: token checks, validation, CSRF, and user persistence."""

from fastapi.testclient import TestClient

from opengsync_db import SyncSession, queries as Q
from opengsync_db.categories import UserRole

from ....conftest import PASSWORD
from ..._profile import new_profile_payload, set_profile, INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL
from ..._http import (
    assert_flash,
    assert_form_invalid,
    assert_htmx_redirect,
    get,
    OpenGSyncTestClient,
    post_form,
    post_form_csrf_mismatch,
)

CSRF_FLASH = "Your form could not be submitted because the security token was invalid or missing"
TOKEN_INVALID_MSG = "Token expired or invalid."
USER_EXISTS_MSG = "User already exists."
NEW_EMAIL = "complete-reg@example.com"


def _token(
    email: str,
    role: UserRole = UserRole.CLIENT,
    valid_minutes: int = 60 * 24,
) -> str:
    from server.core import secrets

    return secrets.generate_registration_token(
        email=email, role=role, valid_minutes=valid_minutes,
    )


def _path(token: str) -> str:
    return f"/htmx/auth/complete-registration/{token}"


def _payload(email: str = NEW_EMAIL, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "email": email,
        "first_name": "Ada",
        "last_name": "Lovelace",
        "password": PASSWORD,
        "confirm": PASSWORD,
        **new_profile_payload(),
    }
    data.update(overrides)
    return data


def _complete(client: TestClient, token: str, **overrides: object):
    from server.core import secrets

    posted_email = overrides.pop("email", None)
    if posted_email is None:
        verified = secrets.verify_registration_token(token)
        posted_email = verified[0] if verified is not None else NEW_EMAIL
    return post_form(client, _path(token), _payload(email=str(posted_email), **overrides))


def test_complete_registration_get_renders_form(client: TestClient):
    token = _token(NEW_EMAIL)
    response = get(client, _path(token))
    assert response.status_code == 200
    assert 'name="email"' in response.text
    assert NEW_EMAIL in response.text
    assert 'name="first_name"' in response.text
    assert 'name="last_name"' in response.text
    assert 'name="password"' in response.text
    assert 'name="confirm"' in response.text
    assert 'name="csrf_token"' in response.text


def test_complete_registration_get_invalid_token_shows_error(client: TestClient):
    response = get(client, _path("not-a-real-token"))
    assert response.status_code == 200
    assert TOKEN_INVALID_MSG in response.text


def test_complete_registration_valid_creates_user_and_redirects(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)

    response = _complete(client, token)

    assert_htmx_redirect(response, contains="/auth/login")
    assert_flash(response, "Registration completed successfully.", category="success")

    session.expire_all()
    created = session.first(Q.user.select(email=NEW_EMAIL))
    assert created is not None
    assert created.first_name == "Ada"
    assert created.last_name == "Lovelace"
    assert created.role == UserRole.CLIENT
    assert created.password != PASSWORD


def test_complete_registration_persists_role_from_token(
    client: TestClient, session: SyncSession,
):
    email = "complete-tech@example.com"
    token = _token(email, role=UserRole.TECHNICIAN)

    response = _complete(client, token, email=email)

    assert_htmx_redirect(response, contains="/auth/login")
    session.expire_all()
    created = session.get_one(Q.user.select(email=email))
    assert created.role == UserRole.TECHNICIAN


def test_complete_registration_can_login_afterwards(client: TestClient):
    token = _token(NEW_EMAIL)
    _complete(client, token)

    login = post_form(
        client,
        "/htmx/auth/login",
        {"email": NEW_EMAIL, "password": PASSWORD},
    )
    assert_htmx_redirect(login, contains="/")
    assert_flash(login, "Logged In!", category="success")


def test_complete_registration_expired_token_rerenders(
    client: TestClient, session: SyncSession,
):
    # Far enough in the past that timezone skew cannot keep the JWT valid.
    # generate_registration_token uses naive datetime.now() for `exp`, which
    # PyJWT treats as UTC — see the report on that mismatch.
    token = _token(NEW_EMAIL, valid_minutes=-60 * 24)

    get_response = get(client, _path(token))
    assert get_response.status_code == 200
    assert TOKEN_INVALID_MSG in get_response.text

    response = _complete(client, token)
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_unknown_token_rerenders(
    client: TestClient, session: SyncSession,
):
    response = _complete(client, "not-a-real-token")
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_password_reset_token_rejected(
    client: TestClient, session: SyncSession, user,
):
    from server.core import secrets

    token = secrets.create_password_reset_token(user.id)
    response = _complete(client, token)
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_already_used_token_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    first = _complete(client, token)
    assert_htmx_redirect(first, contains="/auth/login")

    response = _complete(client, token)
    assert_form_invalid(response, contains=USER_EXISTS_MSG)
    assert session.count(Q.user.select(email=NEW_EMAIL)) == 1


def test_complete_registration_existing_user_rerenders(
    client: TestClient, session: SyncSession, user,
):
    token = _token(user.email)
    before = session.count(Q.user.select())

    response = _complete(client, token, email=user.email)

    assert_form_invalid(response, contains=USER_EXISTS_MSG)
    assert session.count(Q.user.select()) == before


def test_register_existing_user_does_not_issue_completion_link(
    client: OpenGSyncTestClient, fake_mailer, session: SyncSession, user,
):
    response = post_form(client, "/htmx/auth/register", {"email": user.email})

    assert_htmx_redirect(response, contains="/auth/login")
    assert fake_mailer.welcome_back == [user.email]
    assert fake_mailer.registration == []
    before = session.count(Q.user.select())

    assert session.count(Q.user.select()) == before


def test_complete_registration_posted_email_must_match_token(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, email="other@example.com",
    )
    assert_form_invalid(response, contains=TOKEN_INVALID_MSG)
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None
    assert session.first(Q.user.select(email="other@example.com")) is None


def test_complete_registration_short_password_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, password="short", confirm="short",
    )
    assert_form_invalid(response)
    assert "at least 8" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_missing_fields_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = post_form(
        client,
        _path(token),
        {
            "email": NEW_EMAIL,
            "first_name": "",
            "last_name": "",
            "password": "",
            "confirm": "",
        },
    )
    assert_form_invalid(response)
    assert "First Name is required" in response.text
    assert "Last Name is required" in response.text
    assert "Password is required" in response.text
    assert "Confirm Password is required" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_first_name_too_long_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(client, token, first_name="A" * 65)
    assert_form_invalid(response)
    assert "64" in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_password_mismatch_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = _complete(
        client, token, password=PASSWORD, confirm="different-password",
    )
    assert_form_invalid(response, contains="match")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_csrf_mismatch_rerenders(
    client: TestClient, session: SyncSession,
):
    token = _token(NEW_EMAIL)
    response = post_form_csrf_mismatch(client, _path(token), _payload())
    assert_form_invalid(response)
    assert_flash(response, CSRF_FLASH, category="error")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


# ── Organization & PI ───────────────────────────────────────────────────────

_NO_PROFILE = {key: "" for key in new_profile_payload()}


def test_complete_registration_stores_profile(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL))
    assert_htmx_redirect(response, contains="/auth/login")
    user = session.get_one(Q.user.select(email=NEW_EMAIL))
    assert (user.institute, user.department, user.pi_name, user.pi_email) == (INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL)


def test_complete_registration_customer_requires_profile(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL), **_NO_PROFILE)
    assert_form_invalid(response)
    assert "Institute is required." in response.text
    assert "Department is required." in response.text
    assert "Principal Investigator is required." in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_insider_profile_is_optional(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL, role=UserRole.TECHNICIAN), **_NO_PROFILE)
    assert_htmx_redirect(response, contains="/auth/login")
    user = session.get_one(Q.user.select(email=NEW_EMAIL))
    assert user.institute is None and user.pi_email is None


def test_complete_registration_own_pi_stores_own_name_and_email(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL), is_pi="true", **{"pi": "", "pi-text": "", "pi_email": ""})
    assert_htmx_redirect(response, contains="/auth/login")
    user = session.get_one(Q.user.select(email=NEW_EMAIL))
    assert (user.pi_name, user.pi_email) == ("Ada Lovelace", NEW_EMAIL)
    assert user.is_pi and user.profile_complete


def test_complete_registration_own_pi_still_requires_organization(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL), is_pi="true", **_NO_PROFILE)
    assert_form_invalid(response, contains="Institute is required.")
    assert "Principal Investigator is required." not in response.text
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_new_pi_needs_email(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL), pi_email="")
    assert_form_invalid(response, contains="Enter the email of the new PI.")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_new_values_snap_to_existing_spelling(
    client: TestClient, session: SyncSession, user,
):
    set_profile(session, user)
    session.commit()

    response = _complete(
        client, _token(NEW_EMAIL),
        **{
            "institute-text": "  medical  UNIVERSITY of vienna ",
            "department-text": "department of medicine i",
            "pi-text": "G. Hopper",
            "pi_email": "Grace.Hopper@Example.com",
        },
    )
    assert_htmx_redirect(response, contains="/auth/login")
    new_user = session.get_one(Q.user.select(email=NEW_EMAIL))
    assert (new_user.institute, new_user.department) == (INSTITUTE, DEPARTMENT)
    # A PI is identified by the email: the stored name is kept
    assert (new_user.pi_name, new_user.pi_email) == (PI_NAME, PI_EMAIL)


def test_complete_registration_selects_existing_values_by_key(
    client: TestClient, session: SyncSession, user,
):
    from server.core import column_values

    set_profile(session, user)
    session.commit()
    sources = column_values.SOURCES

    response = _complete(
        client, _token(NEW_EMAIL),
        **{
            "institute": column_values.key_of(sources["user_institute"], (INSTITUTE,)), "institute-text": INSTITUTE,
            "department": column_values.key_of(sources["user_department"], (DEPARTMENT,)), "department-text": DEPARTMENT,
            "pi": column_values.key_of(sources["user_pi"], (PI_NAME, PI_EMAIL)), "pi-text": PI_NAME,
            "pi_email": "",
        },
    )
    assert_htmx_redirect(response, contains="/auth/login")
    new_user = session.get_one(Q.user.select(email=NEW_EMAIL))
    assert (new_user.institute, new_user.department, new_user.pi_name, new_user.pi_email) == (
        INSTITUTE, DEPARTMENT, PI_NAME, PI_EMAIL,
    )


def test_complete_registration_unknown_key_rerenders(client: TestClient, session: SyncSession):
    response = _complete(client, _token(NEW_EMAIL), institute="no such institute", **{"institute-text": "X"})
    assert_form_invalid(response, contains="Invalid institute selected.")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None


def test_complete_registration_department_must_be_of_the_institute(
    client: TestClient, session: SyncSession, user, user_2,
):
    from server.core import column_values

    set_profile(session, user)
    set_profile(session, user_2, institute="CeMM", department="Bioinformatics")
    session.commit()
    sources = column_values.SOURCES
    institute = {"institute": column_values.key_of(sources["user_institute"], (INSTITUTE,)), "institute-text": INSTITUTE}
    bioinformatics = column_values.key_of(sources["user_department"], ("Bioinformatics",))

    response = _complete(client, _token(NEW_EMAIL), **institute, department=bioinformatics, **{"department-text": "Bioinformatics"})
    assert_form_invalid(response, contains="Bioinformatics is not a department of Medical University of Vienna")
    assert session.first(Q.user.select(email=NEW_EMAIL)) is None

    # typed as new, it is created at the institute
    response = _complete(client, _token(NEW_EMAIL), **institute, department="new", **{"department-text": "bioinformatics"})
    assert_htmx_redirect(response, contains="/auth/login")
    assert session.get_one(Q.user.select(email=NEW_EMAIL)).department == "bioinformatics"


def test_profile_fields_mark_new_pi_email_required(client: TestClient):
    html = get(client, _path(_token(NEW_EMAIL))).text
    assert 'placeholder="Required"' in html.split('name="pi_email"')[0].rsplit("<input", 1)[1]
