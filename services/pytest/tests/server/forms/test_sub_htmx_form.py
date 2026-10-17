"""SubHTMXForm: field collection, prefixes, nested errors, and Pydantic validation."""

import types

from server.components import inputs
from server.forms.SubHTMXForm import SubHTMXForm


class DetailsSubForm(SubHTMXForm):
    title = "Details"
    order = 1

    name = inputs.string.StringInputField("Name", required=True, max_length=4)
    note = inputs.string.StringInputField("Note", required=False)


def test_fields_are_collected_and_prefixed():
    sub_form = DetailsSubForm(prefix="details")

    assert [field.name for field in sub_form.input_fields] == ["details-name", "details-note"]
    assert [field.id for field in sub_form.input_fields] == ["details-name", "details-note"]
    # Non-field class attributes stay untouched.
    assert sub_form.title == "Details"
    assert sub_form.order == 1


def test_fields_without_prefix_keep_their_names():
    sub_form = DetailsSubForm()

    assert [field.name for field in sub_form.input_fields] == ["name", "note"]


def test_instances_do_not_share_field_state():
    first = DetailsSubForm(prefix="details")
    second = DetailsSubForm(prefix="details")

    first.name.data = "changed"

    assert second.name.data is None
    assert first.name is not second.name


def test_valid_data_populates_fields():
    sub_form = DetailsSubForm()

    assert sub_form.validate({"name": "ok"}) is True

    assert sub_form.validated is True
    assert sub_form.is_valid is True
    assert sub_form.has_errors is False
    assert sub_form.errors == {}
    assert sub_form.name.data == "ok"
    assert sub_form.note.data is None


def test_missing_required_field_records_error():
    sub_form = DetailsSubForm()

    assert sub_form.validate({}) is False

    assert sub_form.errors == {"name": ["Name is required"]}
    assert sub_form.has_errors is True
    assert sub_form.is_valid is False


def test_optional_blank_value_is_normalized_to_none():
    sub_form = DetailsSubForm()

    assert sub_form.validate({"name": "ok", "note": "   "}) is True

    assert sub_form.note.data is None
    assert sub_form.note.raw_data is None


def test_pydantic_length_error_uses_field_label():
    sub_form = DetailsSubForm()

    assert sub_form.validate({"name": "abcdef"}) is False

    assert sub_form.errors == {"name": ["Name should have at most 4 characters"]}


def test_errors_are_cleared_between_validations():
    sub_form = DetailsSubForm()

    assert sub_form.validate({}) is False
    assert sub_form.errors

    assert sub_form.validate({"name": "ok"}) is True

    assert sub_form.errors == {}


def test_populate_from_data_sets_raw_and_validated_values():
    sub_form = DetailsSubForm()

    sub_form.populate_from_data({"name": "from-data"})

    assert sub_form.name.raw_data == "from-data"
    assert sub_form.name.data == "from-data"
    assert sub_form.name._validated is True
    assert sub_form.note.data is None


def test_populate_from_model_strips_prefix_and_honours_mapping():
    model = types.SimpleNamespace(name="model-name", other="mapped-value")

    sub_form = DetailsSubForm(prefix="details")
    sub_form.populate_from_model(model)

    assert sub_form.name.raw_data == "model-name"
    assert sub_form.note.raw_data is None

    mapped = DetailsSubForm(prefix="details")
    mapped.populate_from_model(model, {"name": "other"})

    assert mapped.name.raw_data == "mapped-value"


def test_pydantic_model_is_cached():
    sub_form = DetailsSubForm()

    first = sub_form._build_pydantic_model()
    second = sub_form._build_pydantic_model()

    assert first is second
    assert first.__name__ == "DetailsSubFormModel"

    partial = sub_form._build_pydantic_model([sub_form.name])

    assert partial is not first
    assert partial.__name__ == "DetailsSubFormPartialModel"
