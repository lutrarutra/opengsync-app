"""ColumnValueInputField: keys of existing values, new names, the ``<name>-text`` companion input and prefills."""

import types

import pytest

from server.components import inputs
from server.core import exceptions as exc
from server.forms.HTMXForm import HTMXForm

CSRF = "test-csrf"


class PlaceForm(HTMXForm):
    template_path = "forms/auth/api_token.html"

    place = inputs.column_value.ColumnValueInputField(
        "Institute", source="user_institute", new_min_length=3, new_max_length=10,
    )
    optional_place = inputs.column_value.ColumnValueInputField("Optional Institute", source="user_institute", required=False)
    existing_only = inputs.column_value.ColumnValueInputField(
        "Existing Institute", source="user_institute", required=False, allow_new=False,
    )


def _validate(formdata: dict, form: PlaceForm | None = None) -> PlaceForm:
    form = form or PlaceForm()
    request = types.SimpleNamespace(method="POST", state=types.SimpleNamespace(form_data={"csrf_token": CSRF, **formdata}))
    return PlaceForm.Validate()(request=request, csrf_token=CSRF, form=form)


def _errors(formdata: dict) -> dict:
    form = PlaceForm()
    with pytest.raises(exc.FormValidationException):
        _validate(formdata, form)
    return form.errors


def test_key_is_kept_with_its_shown_name():
    form = _validate({"place": "cemm", "place-text": " CeMM "})

    assert form.place.data == "cemm"
    assert form.place.is_new is False
    assert form.place.value == "cemm"
    assert form.place.display_text == "CeMM"


def test_new_name_has_whitespace_collapsed():
    form = _validate({"place": "new", "place-text": "  New   Place "})

    assert form.place.data == "New Place"
    assert form.place.is_new is True
    assert form.place.value == "new"
    assert form.place.display_text == "New Place"


@pytest.mark.parametrize(("text", "error"), [
    ("", "Enter a name for the new institute."),
    ("ab", "Institute should have at least 3 characters."),
    ("a" * 11, "Institute should have at most 10 characters."),
])
def test_new_name_is_checked(text: str, error: str):
    assert _errors({"place": "new", "place-text": text})["place"] == [error]


def test_required_and_optional():
    assert _errors({"place": ""})["place"] == ["Institute is required"]
    form = _validate({"place": "cemm", "optional_place": ""})
    assert form.optional_place.data is None
    assert form.optional_place.value == ""


def test_new_name_rejected_without_allow_new():
    errors = _errors({"place": "cemm", "existing_only": "new", "existing_only-text": "Somewhere"})
    assert errors["existing_only"] == ["Select an existing existing institute."]


def test_set_values_prefills_key_and_name():
    form = PlaceForm()
    form.place.set_values((" Medical  University ",))
    assert form.place.value == "medical university"
    assert form.place.display_text == " Medical  University "

    form.place.set_values((None,))
    assert form.place.value == "" and form.place.display_text == ""


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError):
        inputs.column_value.ColumnValueInputField("X", source="nope")
