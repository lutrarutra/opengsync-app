"""SearchableInputField: ids, new names (``allow_new``), the ``<name>-text`` companion input and prefills."""

import types

import pytest

from server.components import inputs
from server.core import exceptions as exc
from server.forms.HTMXForm import HTMXForm
from server.forms.SubHTMXForm import SubHTMXForm

CSRF = "test-csrf"


class ThingForm(HTMXForm):
    template_path = "forms/auth/api_token.html"

    thing = inputs.searchable.SearchableInputField(
        "Thing", route="search_projects", allow_new=True, new_min_length=3, new_max_length=10,
    )
    optional_thing = inputs.searchable.SearchableInputField(
        "Optional Thing", route="search_projects", required=False, allow_new=True,
    )
    plain = inputs.searchable.SearchableInputField("Plain", route="search_projects", required=False)


class ThingSubForm(SubHTMXForm):
    thing = inputs.searchable.SearchableInputField("Thing", route="search_projects", allow_new=True)


def _validate(formdata: dict, form: ThingForm | None = None) -> ThingForm:
    form = form or ThingForm()
    request = types.SimpleNamespace(method="POST", state=types.SimpleNamespace(form_data={"csrf_token": CSRF, **formdata}))
    return ThingForm.Validate()(request=request, csrf_token=CSRF, form=form)


def _errors(formdata: dict) -> dict:
    form = ThingForm()
    with pytest.raises(exc.FormValidationException):
        _validate(formdata, form)
    return form.errors


def test_id_is_an_int_with_its_shown_name():
    form = _validate({"thing": "12", "thing-text": " Thing 12 "})

    assert form.thing.data == 12
    assert form.thing.is_new is False
    assert form.thing.value == "12"
    assert form.thing.display_text == "Thing 12"


def test_new_name_is_stripped_text():
    form = _validate({"thing": "new", "thing-text": "  Fresh  "})

    assert form.thing.data == "Fresh"
    assert form.thing.is_new is True
    assert form.thing.value == "new"
    assert form.thing.display_text == "Fresh"


def test_new_name_of_digits_stays_a_new_name():
    form = _validate({"thing": "new", "thing-text": "123456"})

    assert form.thing.data == "123456"
    assert form.thing.is_new is True
    assert form.thing.value == "new"


@pytest.mark.parametrize(("text", "error"), [
    ("", "Enter a name for the new thing."),
    ("   ", "Enter a name for the new thing."),
    ("ab", "Thing should have at least 3 characters."),
    ("a" * 11, "Thing should have at most 10 characters."),
])
def test_invalid_new_names_are_rejected(text: str, error: str):
    assert _errors({"thing": "new", "thing-text": text}) == {"thing": [error]}


def test_garbage_value_is_rejected():
    assert _errors({"thing": "abc"}) == {"thing": ["Invalid thing selected."]}


def test_missing_required_value_is_reported_once():
    assert _errors({}) == {"thing": ["Thing is required"]}


def test_missing_optional_value_is_none():
    form = _validate({"thing": "1"})

    assert form.optional_thing.data is None
    assert form.optional_thing.is_new is False
    assert form.optional_thing.value == ""


def test_new_value_without_allow_new_is_rejected():
    errors = _errors({"thing": "1", "plain": "new", "plain-text": "Fresh"})

    assert list(errors) == ["plain"]


def test_without_allow_new_ids_are_validated_and_names_kept():
    form = _validate({"thing": "1", "plain": "7", "plain-text": "Seven"})

    assert form.plain.data == 7
    assert form.plain.is_new is False
    assert form.plain.display_text == "Seven"


def test_values_are_kept_for_the_rerender_after_another_fields_error():
    form = ThingForm()
    with pytest.raises(exc.FormValidationException):
        _validate({"thing": "new", "thing-text": "x", "optional_thing": "new", "optional_thing-text": "Kept"}, form)

    assert form.thing.value == "new" and form.thing.display_text == "x"
    assert form.optional_thing.data == "Kept"
    assert form.optional_thing.value == "new" and form.optional_thing.display_text == "Kept"


def test_prefill_helpers():
    form = ThingForm()

    form.thing.set_selected(5, "Five")
    assert (form.thing.data, form.thing.value, form.thing.display_text, form.thing.is_new) == (5, "5", "Five", False)

    form.thing.set_new("Brand New")
    assert (form.thing.data, form.thing.value, form.thing.display_text, form.thing.is_new) == ("Brand New", "new", "Brand New", True)

    form.thing.set_selected(None)
    assert (form.thing.data, form.thing.value, form.thing.display_text) == (None, "", "")


def test_sub_form_uses_the_prefixed_text_input():
    sub = ThingSubForm(prefix="rows-0")

    assert sub.thing.name == "rows-0-thing"
    assert sub.thing.text_name == "rows-0-thing-text"
    assert sub.validate({"rows-0-thing": "new", "rows-0-thing-text": " Sub Thing "}) is True
    assert sub.thing.data == "Sub Thing" and sub.thing.is_new is True


def test_sub_form_rerender_from_submitted_data_keeps_the_new_name():
    """Re-rendered sub-forms hold the submitted value ("new"), not the validated name."""
    sub = ThingSubForm(prefix="rows-0")
    data = {"rows-0-thing": "new", "rows-0-thing-text": "Sub Thing"}
    sub.validate(data)

    sub.populate_from_data(data)

    assert sub.thing.is_new is True
    assert sub.thing.value == "new"
    assert sub.thing.display_text == "Sub Thing"


def test_sub_form_rerender_from_submitted_data_keeps_the_id():
    sub = ThingSubForm(prefix="rows-0")
    data = {"rows-0-thing": "3", "rows-0-thing-text": "Three"}
    sub.validate(data)

    sub.populate_from_data(data)

    assert sub.thing.is_new is False
    assert sub.thing.value == "3"
    assert sub.thing.display_text == "Three"
