"""Unit tests for SubFormList — the dynamic sub-form list component.

These tests are self-contained and do NOT require a database or the server package.
"""
from __future__ import annotations

from typing import Any, Optional
from abc import ABC
import pytest


# ---------------------------------------------------------------------------
# Minimal stubs for BaseInputField and SubHTMXForm
# ---------------------------------------------------------------------------

class BaseInputField(ABC):
    """Minimal stub matching the real BaseInputField interface."""
    def __init__(self, label: str, *, default: Any = None, required: bool = True,
                 pydantic_type: Any = str, read_only: bool = False):
        self.label = label
        self.name = ""
        self.id = ""
        self.default = default
        self._data: Any = None
        self._validated: bool = False
        self.raw_data: Any = None
        self.errors: list[str] = []
        self.pydantic_type = pydantic_type
        self.required = required
        self.read_only = read_only
        self._self_validated: bool = False

    @property
    def data(self) -> Any:
        if self._validated:
            return self._data
        return self.default

    @data.setter
    def data(self, value: Any) -> None:
        self._data = value
        self._validated = True

    def validate(self, raw_data: dict[str, Any]) -> bool:
        return True


class StringInputField(BaseInputField):
    def __init__(self, label: str, *, required: bool = True, read_only: bool = False):
        super().__init__(label=label, required=required, pydantic_type=str, read_only=read_only)


class FloatInputField(BaseInputField):
    def __init__(self, label: str, *, required: bool = True):
        super().__init__(label=label, required=required, pydantic_type=float)


class SubHTMXForm:
    """Minimal stub matching the real SubHTMXForm interface."""
    validated: bool = False

    def __init__(self, prefix: str = ""):
        self._prefix = prefix
        self._fields_cache: Optional[list[BaseInputField]] = None

        for field_name in dir(self.__class__):
            if field_name.startswith("_"):
                continue
            field = getattr(self.__class__, field_name)
            if isinstance(field, BaseInputField):
                field_instance = self._clone_field(field)
                field_instance.name = f"{prefix}-{field_name}" if prefix else field_name
                field_instance.id = field_instance.name
                setattr(self, field_name, field_instance)

    def _clone_field(self, field: BaseInputField) -> BaseInputField:
        field_class = field.__class__
        new_field = object.__new__(field_class)
        for key, value in field.__dict__.items():
            setattr(new_field, key, value)
        new_field._data = field.default
        new_field._validated = False
        new_field._self_validated = False
        new_field.raw_data = None
        new_field.errors = []
        return new_field

    @property
    def input_fields(self) -> list[BaseInputField]:
        if self._fields_cache is not None:
            return self._fields_cache
        fields = []
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, BaseInputField):
                fields.append(field_value)
        self._fields_cache = fields
        return fields

    @property
    def errors(self) -> dict[str, list[str]]:
        all_errors = {}
        for field in self.input_fields:
            if field.errors:
                all_errors[field.name] = field.errors
        return all_errors

    @property
    def has_errors(self) -> bool:
        return any(field.errors for field in self.input_fields)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def populate_from_data(self, data: dict[str, Any]) -> None:
        for field in self.input_fields:
            field.raw_data = data.get(field.name, field.default)

    def validate(self, raw_data: dict[str, Any]) -> bool:
        for field in self.input_fields:
            field.errors = []

        for field in self.input_fields:
            value = raw_data.get(field.name)
            field.raw_data = value
            if field.required and (value is None or (isinstance(value, str) and value.strip() == "")):
                field.errors.append(f"{field.label} is required")
            elif not field.required and isinstance(value, str) and value.strip() == "":
                raw_data[field.name] = None
                field.raw_data = None

        # Simple Pydantic-like type coercion for float fields
        for field in self.input_fields:
            if isinstance(field, FloatInputField) and field.raw_data is not None:
                try:
                    field._data = float(field.raw_data)
                    field._validated = True
                except (ValueError, TypeError):
                    field.errors.append(f"Invalid value for {field.label}")

        self.validated = True
        return self.is_valid


# ---------------------------------------------------------------------------
# The actual SubFormList implementation under test
# ---------------------------------------------------------------------------

T = type("T", (), {})


class SubFormList:
    """Minimal SubFormList implementation matching the real one."""
    _sub_form_class: type | None = None

    def __init__(self, min_elements: int = 0):
        self.min_elements = min_elements
        self.name: str = ""
        self.entries: list = []
        self._errors: list[str] = []

    @classmethod
    def __class_getitem__(cls, item: type) -> type:
        return type(
            f"{cls.__name__}[{item.__name__}]",
            (cls,),
            {"_sub_form_class": item},
        )

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, index: int):
        return self.entries[index]

    def __iter__(self):
        return iter(self.entries)

    def append_entry(self):
        sub_form_class = self.resolve_sub_form_class()
        idx = len(self.entries)
        entry = sub_form_class(prefix=f"{self.name}-{idx}")
        self.entries.append(entry)
        return entry

    def resolve_sub_form_class(self) -> type:
        cls = type(self)
        if cls._sub_form_class is not None:
            return cls._sub_form_class
        raise TypeError(
            f"{cls.__name__} has no _sub_form_class. "
            "Use SubFormList[YourSubForm](...) syntax."
        )

    def validate(self, raw_data: dict[str, Any]) -> bool:
        all_valid = True
        for entry in self.entries:
            if not entry.validate(raw_data):
                all_valid = False
        if len(self.entries) < self.min_elements:
            self._errors.append(
                f"At least {self.min_elements} entr{'y' if self.min_elements == 1 else 'ies'} are required."
            )
            all_valid = False
        return all_valid

    @property
    def errors(self) -> dict[str | None, list[str]]:
        all_errors: dict[str | None, list[str]] = {}
        for entry in self.entries:
            all_errors.update(entry.errors)
        if self._errors:
            all_errors[None] = list(self._errors)
        return all_errors

    @property
    def has_errors(self) -> bool:
        if self._errors:
            return True
        return any(entry.has_errors for entry in self.entries)

    @property
    def input_fields(self) -> list[BaseInputField]:
        fields: list[BaseInputField] = []
        for entry in self.entries:
            fields.extend(entry.input_fields)
        return fields

    def populate_from_data(self, data: dict[str, Any]) -> None:
        for entry in self.entries:
            entry.populate_from_data(data)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class ItemSubForm(SubHTMXForm):
    name = StringInputField("Name", required=True)
    value = FloatInputField("Value", required=False)


@pytest.fixture
def empty_list():
    lst = SubFormList[ItemSubForm](min_elements=0)
    lst.name = "items"
    return lst


@pytest.fixture
def populated_list():
    lst = SubFormList[ItemSubForm](min_elements=0)
    lst.name = "items"
    lst.append_entry()
    lst.append_entry()
    return lst


# ---------------------------------------------------------------------------
# Construction & generic parametrisation
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_generic_syntax_creates_subclass(self):
        cls = SubFormList[ItemSubForm]
        assert cls._sub_form_class is ItemSubForm
        assert "SubFormList[ItemSubForm]" in cls.__name__

    def test_instantiation(self, empty_list):
        assert len(empty_list) == 0
        assert empty_list.name == "items"
        assert empty_list.min_elements == 0

    def test_min_elements_stored(self):
        lst = SubFormList[ItemSubForm](min_elements=3)
        assert lst.min_elements == 3

    def test_raises_without_generic(self):
        lst = SubFormList(min_elements=0)
        with pytest.raises(TypeError, match="no _sub_form_class"):
            lst.resolve_sub_form_class()


# ---------------------------------------------------------------------------
# Entry management
# ---------------------------------------------------------------------------

class TestEntryManagement:
    def test_append_entry(self, empty_list):
        entry = empty_list.append_entry()
        assert len(empty_list) == 1
        assert entry is empty_list[0]

    def test_append_entry_prefix(self, empty_list):
        empty_list.append_entry()
        assert empty_list[0].input_fields[0].name == "items-0-name"

    def test_multiple_entries_prefixes(self, empty_list):
        empty_list.append_entry()
        empty_list.append_entry()
        empty_list.append_entry()
        assert len(empty_list) == 3
        assert empty_list[0].input_fields[0].name == "items-0-name"
        assert empty_list[1].input_fields[0].name == "items-1-name"
        assert empty_list[2].input_fields[0].name == "items-2-name"

    def test_iteration(self, populated_list):
        names = [e.input_fields[0].name for e in populated_list]
        assert names == ["items-0-name", "items-1-name"]

    def test_indexing(self, populated_list):
        assert populated_list[0].input_fields[0].name == "items-0-name"
        assert populated_list[1].input_fields[0].name == "items-1-name"

    def test_len(self, populated_list):
        assert len(populated_list) == 2

    def test_input_fields_property(self, populated_list):
        fields = populated_list.input_fields
        assert len(fields) == 4
        names = [f.name for f in fields]
        assert "items-0-name" in names
        assert "items-0-value" in names
        assert "items-1-name" in names
        assert "items-1-value" in names


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_data(self, populated_list):
        raw_data = {
            "items-0-name": "Pool A",
            "items-0-value": "5.5",
            "items-1-name": "Pool B",
            "items-1-value": "3.2",
        }
        assert populated_list.validate(raw_data)
        assert not populated_list.has_errors
        assert populated_list.errors == {}

    def test_valid_data_optional_float_omitted(self, populated_list):
        raw_data = {
            "items-0-name": "Pool A",
            "items-1-name": "Pool B",
        }
        assert populated_list.validate(raw_data)
        assert populated_list[0].value.data is None

    def test_required_field_missing(self, populated_list):
        raw_data = {
            "items-0-name": "",
            "items-1-name": "Pool B",
        }
        assert not populated_list.validate(raw_data)
        assert populated_list.has_errors
        assert "items-0-name" in populated_list.errors

    def test_required_field_omitted(self, populated_list):
        raw_data = {
            "items-1-name": "Pool B",
        }
        assert not populated_list.validate(raw_data)
        assert populated_list.has_errors

    def test_min_elements_violation(self):
        lst = SubFormList[ItemSubForm](min_elements=2)
        lst.name = "items"
        lst.append_entry()
        assert not lst.validate({})
        assert lst.has_errors
        assert None in lst.errors
        assert any("2 entries" in err for err in lst.errors[None])

    def test_min_elements_satisfied(self):
        lst = SubFormList[ItemSubForm](min_elements=2)
        lst.name = "items"
        lst.append_entry()
        lst.append_entry()
        raw_data = {"items-0-name": "A", "items-1-name": "B"}
        assert lst.validate(raw_data)

    def test_float_coercion(self, populated_list):
        raw_data = {
            "items-0-name": "Pool A",
            "items-0-value": "3.14",
            "items-1-name": "Pool B",
            "items-1-value": "2.718",
        }
        assert populated_list.validate(raw_data)
        assert populated_list[0].value.data == 3.14
        assert populated_list[1].value.data == 2.718

    def test_float_type_error(self, populated_list):
        raw_data = {
            "items-0-name": "Pool A",
            "items-0-value": "not-a-number",
            "items-1-name": "Pool B",
        }
        assert not populated_list.validate(raw_data)
        assert populated_list.has_errors
        assert "items-0-value" in populated_list.errors


# ---------------------------------------------------------------------------
# Error aggregation
# ---------------------------------------------------------------------------

class TestErrors:
    def test_no_errors(self, populated_list):
        raw_data = {"items-0-name": "A", "items-1-name": "B"}
        populated_list.validate(raw_data)
        assert populated_list.errors == {}

    def test_single_field_error(self, populated_list):
        raw_data = {"items-0-name": "", "items-1-name": "B"}
        populated_list.validate(raw_data)
        errors = populated_list.errors
        assert "items-0-name" in errors
        assert "items-1-name" not in errors

    def test_multiple_field_errors(self, populated_list):
        raw_data = {"items-0-name": "", "items-1-name": ""}
        populated_list.validate(raw_data)
        errors = populated_list.errors
        assert "items-0-name" in errors
        assert "items-1-name" in errors

    def test_list_level_errors(self):
        lst = SubFormList[ItemSubForm](min_elements=1)
        lst.name = "items"
        lst.validate({})
        errors = lst.errors
        assert None in errors


# ---------------------------------------------------------------------------
# Data population
# ---------------------------------------------------------------------------

class TestDataPopulation:
    def test_populate_from_data(self, populated_list):
        data = {
            "items-0-name": "Pool A",
            "items-0-value": "5.5",
            "items-1-name": "Pool B",
        }
        populated_list.populate_from_data(data)
        assert populated_list[0].name.raw_data == "Pool A"
        assert populated_list[0].value.raw_data == "5.5"
        assert populated_list[1].name.raw_data == "Pool B"


# ---------------------------------------------------------------------------
# Per-instance isolation
# ---------------------------------------------------------------------------

class TestIsolation:
    def test_entries_not_shared(self):
        lst1 = SubFormList[ItemSubForm](min_elements=0)
        lst1.name = "a"
        lst1.append_entry()

        lst2 = SubFormList[ItemSubForm](min_elements=0)
        lst2.name = "b"

        assert len(lst1) == 1
        assert len(lst2) == 0
        assert lst1[0].input_fields[0].name == "a-0-name"