"""HTMXForm infrastructure: route registration, Init()/Validate() deps, field state."""

import types

import pytest
from fastapi.testclient import TestClient

from server.components import inputs
from server.core import exceptions as exc
from server.forms.HTMXForm import HTMXForm, _class_name_to_path, htmx_route
from server.forms.auth.APITokenForm import APITokenForm

CSRF = "test-csrf"


class SampleForm(HTMXForm):
    template_path = "forms/auth/api_token.html"

    name = inputs.string.StringInputField("Name", required=True, max_length=5)
    nickname = inputs.string.StringInputField("Nickname", required=False)
    confirm = inputs.boolean.BooleanInputField("Confirm")

    @htmx_route("GET", "/begin")
    def Begin(cls):
        def route():
            return None

        return route

    @htmx_route("POST", "/begin")
    def Submit(cls):
        def route():
            return None

        return route


class ChildForm(SampleForm):
    @htmx_route("POST", "/other")
    def Submit(cls):
        def route():
            return None

        return route


class DefaultPathForm(HTMXForm):
    @htmx_route("GET")
    def Begin(cls):
        def route():
            return None

        return route


def _validate(
    formdata: dict,
    *,
    csrf_cookie: str | None = CSRF,
    method: str = "POST",
    form: HTMXForm | None = None,
):
    form = form or SampleForm()
    dependency = SampleForm.Validate()
    request = types.SimpleNamespace(
        method=method,
        state=types.SimpleNamespace(form_data=formdata),
    )
    return dependency(request=request, csrf_token=csrf_cookie, form=form)


def _valid_data(**overrides) -> dict:
    data = {"name": "ok", "nickname": "", "confirm": "on", "csrf_token": CSRF}
    data.update(overrides)
    return data


@pytest.mark.parametrize(
    "class_name,expected",
    [
        ("QCLanesForm", "/q-c-lanes"),
        ("ProjectSelectForm", "/project-select"),
        ("MultiStepForm", "/multi-step"),
        ("SampleAnnotationForm", "/sample-annotation"),
        ("BarcodeInputForm", "/barcode-input"),
    ],
)
def test_class_name_to_path(class_name: str, expected: str):
    assert _class_name_to_path(class_name) == expected


def test_default_path_and_name_use_the_class_name():
    (route,) = DefaultPathForm._routes

    assert route.path == "/default-path"
    assert route.name == "DefaultPathForm.Begin"
    assert route.method == "GET"


def test_declared_routes_are_collected():
    routes = {route.func_name: route for route in SampleForm._routes}

    assert set(routes) == {"Begin", "Submit"}
    assert routes["Begin"].name == "SampleForm.Begin"
    assert routes["Begin"].method == "GET"
    assert routes["Begin"].path == "/begin"
    assert routes["Submit"].name == "SampleForm.Submit"
    assert routes["Submit"].method == "POST"


def test_child_form_inherits_and_overrides_routes():
    routes = {route.func_name: route for route in ChildForm._routes}

    assert set(routes) == {"Begin", "Submit"}
    # Inherited routes keep the base class name.
    assert routes["Begin"].name == "SampleForm.Begin"
    assert routes["Begin"].path == "/begin"
    # Overridden routes get the child name and path.
    assert routes["Submit"].name == "ChildForm.Submit"
    assert routes["Submit"].path == "/other"
    # The base class definition is untouched.
    assert {route.func_name: route.path for route in SampleForm._routes}["Submit"] == "/begin"


def test_router_registers_endpoints_with_declared_names():
    router = SampleForm.Router()

    registered = {(route.name, tuple(sorted(route.methods)), route.path) for route in router.routes}

    assert registered == {
        ("SampleForm.Begin", ("GET",), "/begin"),
        ("SampleForm.Submit", ("POST",), "/begin"),
    }


def test_router_prefix_is_applied_to_names():
    router = SampleForm.Router(prefix="samples")

    assert {route.name for route in router.routes} == {
        "samples.SampleForm.Begin",
        "samples.SampleForm.Submit",
    }


def test_api_token_form_routes_are_registered_on_the_app(client: TestClient):
    declared = {(route.method, route.path, route.name) for route in APITokenForm._routes}
    assert declared == {
        ("GET", "/{user_id}/create-api-token", "APITokenForm.Begin"),
        ("POST", "/{user_id}/create-api-token", "APITokenForm.Create"),
    }

    app_names = {getattr(route, "name", None) for route in client.app.router.routes}
    assert {"APITokenForm.Begin", "APITokenForm.Create"} <= app_names
    assert client.app.url_path_for("APITokenForm.Begin", user_id=7) == "/htmx/users/7/create-api-token"


def test_init_dependency_returns_fresh_isolated_forms():
    dependency = SampleForm.Init()

    first = dependency()
    second = dependency()

    assert isinstance(first, SampleForm)
    assert first is not second
    first.name.data = "changed"
    assert second.name.data is None
    assert first.name is not second.name


def test_init_returns_a_callable_dependency():
    assert callable(SampleForm.Init())


def test_validate_returns_the_form_on_valid_submission():
    form = SampleForm()

    validated = _validate(_valid_data(), form=form)

    assert validated is form
    assert form.validated is True
    assert form.is_valid is True
    assert form.name.data == "ok"
    assert form.nickname.data is None
    assert form.confirm.data is True


def test_validate_empty_optional_is_stored_as_none():
    form = SampleForm()

    _validate(_valid_data(nickname="   "), form=form)

    assert form.nickname.data is None
    assert form.raw_data["nickname"] is None


def test_validate_missing_checkbox_is_false():
    form = SampleForm()

    _validate({"name": "ok", "csrf_token": CSRF}, form=form)

    assert form.confirm.data is False


def test_validate_requires_a_matching_csrf_pair():
    form = SampleForm()

    with pytest.raises(exc.FormValidationException) as excinfo:
        _validate(_valid_data(csrf_token="other-token"), form=form)

    assert excinfo.value.form is form
    assert form.csrf_token.errors == ["Invalid or missing CSRF token."]
    assert "security token" in (excinfo.value.flash_message or "")


def test_validate_requires_the_csrf_cookie():
    with pytest.raises(exc.FormValidationException):
        _validate(_valid_data(), csrf_cookie=None)


def test_validate_rejects_non_submission_methods():
    with pytest.raises(exc.OpeNGSyncServerException):
        _validate(_valid_data(), method="GET")


def test_validate_reports_missing_required_field():
    form = SampleForm()

    with pytest.raises(exc.FormValidationException) as excinfo:
        _validate({"nickname": "", "csrf_token": CSRF}, form=form)

    assert excinfo.value.flash_message is None
    assert form.errors == {"name": ["Name is required"]}


def test_validate_reports_pydantic_length_error_with_field_label():
    form = SampleForm()

    with pytest.raises(exc.FormValidationException):
        _validate(_valid_data(name="abcdef"), form=form)

    assert form.errors == {"name": ["Name should have at most 5 characters"]}
    # Submitted value is preserved for re-rendering.
    assert form.name.data == "abcdef"


def test_validate_clears_previous_errors_on_resubmission():
    form = SampleForm()

    with pytest.raises(exc.FormValidationException):
        _validate({"nickname": "", "csrf_token": CSRF}, form=form)
    assert form.errors

    _validate(_valid_data(), form=form)

    assert form.errors == {}
    assert form.is_valid is True
