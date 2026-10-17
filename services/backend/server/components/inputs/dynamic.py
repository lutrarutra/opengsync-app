from __future__ import annotations

from typing import Any, Generic, TypeVar, TYPE_CHECKING

from .BaseInputField import BaseInputField

if TYPE_CHECKING:
    from ...forms.SubHTMXForm import SubHTMXForm

T = TypeVar("T", bound="SubHTMXForm")


class SubFormList(Generic[T]):
    """A dynamic list of SubHTMXForm entries, analogous to WTForms FieldList.

    Declared at the class level on an HTMXForm subclass::

        class PoolMappingForm(HTMXWorkflowStep):
            pool_forms: list[PoolMappingSubForm] = SubFormList[PoolMappingSubForm](min_elements=0)

    ``SubFormList`` is a per-instance container.  Each entry is a clone of the
    provided sub-form class with a stable prefix (``{list_name}-{index}``) so
    that submitted form-data keys are deterministic.

    The list supports iteration, indexing, ``len()``, and ``append_entry()``.
    Validation delegates to each entry's ``SubHTMXForm.validate()``.
    """

    _sub_form_class: type | None = None
    """Set by ``__class_getitem__`` on the dynamically created subclass."""

    def __init__(self, min_elements: int = 0):
        self.min_elements = min_elements
        self.name: str = ""
        self.entries: list[T] = []
        self._errors: list[str] = []

    # ---- class-level parametrisation -----------------------------------

    @classmethod
    def __class_getitem__(cls, item: type) -> type[SubFormList]:
        """Support ``SubFormList[SomeSubForm]`` syntax.

        Returns a new subclass with ``_sub_form_class`` set to *item*.
        """
        return type(
            f"{cls.__name__}[{item.__name__}]",
            (cls,),
            {"_sub_form_class": item},
        )

    # ---- list-like interface -------------------------------------------

    def __len__(self) -> int:
        return len(self.entries)

    def __getitem__(self, index: int) -> T:
        return self.entries[index]

    def __iter__(self):
        return iter(self.entries)

    def append_entry(self) -> T:
        """Create a new entry and append it to the list.

        The entry's prefix is ``{self.name}-{index}``, which produces
        form-data keys like ``pool_forms-0-new_pool_name``.
        """
        sub_form_class = self.resolve_sub_form_class()
        idx = len(self.entries)
        entry: T = sub_form_class(prefix=f"{self.name}-{idx}")
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

    # ---- validation ----------------------------------------------------

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Validate every entry and check the minimum count.

        Returns ``True`` if all entries are valid and the count meets
        ``min_elements``.
        """
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

    # ---- error aggregation ---------------------------------------------

    @property
    def errors(self) -> dict[str | None, list[str]]:
        """Aggregate errors from all entries plus list-level errors."""
        all_errors: dict[str | None, list[str]] = {}
        for entry in self.entries:
            all_errors.update(entry.errors)
        if self._errors:
            all_errors[None] = list(self._errors)
        return all_errors

    @property
    def has_errors(self) -> bool:
        """Check if any entry or the list itself has errors."""
        if self._errors:
            return True
        return any(entry.has_errors for entry in self.entries)

    # ---- field access --------------------------------------------------

    @property
    def input_fields(self) -> list[BaseInputField]:
        """Flatten all input fields from all entries."""
        fields: list[BaseInputField] = []
        for entry in self.entries:
            fields.extend(entry.input_fields)
        return fields

    # ---- data population -----------------------------------------------

    def populate_from_data(self, data: dict[str, Any]) -> None:
        """Populate all entries from a data dictionary."""
        for entry in self.entries:
            entry.populate_from_data(data)

    def hydrate_from_data(self, data: dict[str, Any]) -> None:
        """Rebuild entries from submitted form data if the list is empty.

        Called by ``HTMXForm.make_response()`` when re-rendering after a
        failed validation, so that dynamically-created sub-form entries
        (e.g. one per pool) are restored from the submitted field names
        even though ``prepare()`` was never called.
        """
        if self.entries:
            return

        # Discover indexes from keys like "{name}-0-field", "{name}-1-field", ...
        prefix = f"{self.name}-"
        indexes: set[int] = set()
        for key in data:
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            dash = rest.find("-")
            if dash <= 0:
                continue
            try:
                indexes.add(int(rest[:dash]))
            except ValueError:
                continue

        for idx in sorted(indexes):
            entry = self.append_entry()
            entry.populate_from_data(data)