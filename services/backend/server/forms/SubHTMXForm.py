from typing import Any, Optional
from pydantic import BaseModel, ValidationError, create_model

from ..components import inputs


class SubHTMXForm:
    """A sub-form that can be composed into an HTMXForm.

    Each SubHTMXForm represents a logical section of the form,
    typically rendered as an accordion section.

    Example:
        class BasicInfoSubForm(SubHTMXForm):
            title = "Request Info"
            order = 1
            collapsed = False
            icon = "bi-info-circle"

            name = StringInputField("Request Name", required=True)
            description = TextAreaInputField("Description", required=False)
    """
    validated: bool = False

    def __init__(self, prefix: str = ""):
        self._prefix = prefix
        self._fields_cache: Optional[list[inputs.BaseInputField]] = None
        self._pydantic_model: Optional[type[BaseModel]] = None

        for field_name in dir(self.__class__):
            if field_name.startswith("_"):
                continue

            field = getattr(self.__class__, field_name)
            if isinstance(field, inputs.BaseInputField):
                field_instance = self._clone_field(field)
                field_instance.name = f"{prefix}-{field_name}" if prefix else field_name
                field_instance.id = field_instance.name
                setattr(self, field_name, field_instance)

    def _clone_field(self, field: inputs.BaseInputField) -> inputs.BaseInputField:
        """Clone a field instance to avoid shared state between form instances"""
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
    def input_fields(self) -> list[inputs.BaseInputField]:
        """Get all InputField instances in this sub-form"""
        if self._fields_cache is not None:
            return self._fields_cache

        fields = []
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, inputs.BaseInputField):
                fields.append(field_value)

        self._fields_cache = fields
        return fields

    @property
    def errors(self) -> dict[str, list[str]]:
        """Get all errors from all fields"""
        all_errors = {}
        for field in self.input_fields:
            if field.errors:
                all_errors[field.name] = field.errors
        return all_errors

    @property
    def has_errors(self) -> bool:
        """Check if any field has errors"""
        return any(field.errors for field in self.input_fields)

    @property
    def is_valid(self) -> bool:
        """Check if all fields are valid"""
        return len(self.errors) == 0

    def populate_from_data(self, data: dict[str, Any]) -> None:
        """Populate fields from a data dictionary"""
        for field in self.input_fields:
            field.raw_data = data.get(field.name, field.default)

    def populate_from_model(
        self, model: Any, field_mapping: dict[str, str] | None = None
    ) -> None:
        """Populate fields from a model object.

        Args:
            model: The model object to populate from
            field_mapping: Optional mapping of field_name -> model_attribute_name
        """
        for field in self.input_fields:
            key = field.name
            if self._prefix and field.name.startswith(f"{self._prefix}-"):
                key = field.name[len(self._prefix) + 1 :]

            if field_mapping and key in field_mapping:
                attr_name = field_mapping[key]
            else:
                attr_name = key

            value = getattr(model, attr_name, None)
            if value is not None:
                field.raw_data = value

    def _build_pydantic_model(self, fields: list[inputs.BaseInputField] | None = None) -> type[BaseModel]:
        """Dynamically build a Pydantic model from InputFields"""
        if fields is None and self._pydantic_model is not None:
            return self._pydantic_model

        if fields is None:
            fields = self.input_fields

        field_definitions = {}
        for field in fields:
            pydantic_key = field.name.replace("-", "_")
            if field.required:
                default_value = ... if field.default is None else field.default
                field_definitions[pydantic_key] = (field.pydantic_type, default_value)
            else:
                field_definitions[pydantic_key] = (
                    field.pydantic_type | None,
                    field.default,
                )

        if fields is self.input_fields or fields == self.input_fields:
            self._pydantic_model = create_model(
                f"{self.__class__.__name__}Model", **field_definitions
            )
            return self._pydantic_model

        return create_model(
            f"{self.__class__.__name__}PartialModel", **field_definitions
        )

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Validate the sub-form data.

        Returns True if valid, False otherwise.
        Sets errors on fields that fail validation.
        """
        for field in self.input_fields:
            field.errors = []

        for field in self.input_fields:
            value = raw_data.get(field.name)
            field.raw_data = value
            if field.required and (
                value is None or (isinstance(value, str) and value.strip() == "")
            ):
                field.errors.append(f"{field.label} is required")
            elif not field.required and isinstance(value, str) and value.strip() == "":
                raw_data[field.name] = None
                field.raw_data = None

        # Fields that implement their own validate() (e.g. SpreadsheetInputField)
        # are validated here and excluded from Pydantic validation below.
        pydantic_fields = []
        for field in self.input_fields:
            if field.validate(raw_data):
                if not field._self_validated:
                    pydantic_fields.append(field)

        PydanticModel = self._build_pydantic_model(pydantic_fields)

        try:
            mapped_data = {}
            for field in pydantic_fields:
                pydantic_key = field.name.replace("-", "_")
                raw_value = raw_data.get(field.name, field.default)

                if isinstance(field, inputs.BooleanInputField):
                    raw_value = field.validate_value(raw_value)

                mapped_data[pydantic_key] = raw_value

            validated_data = PydanticModel(**mapped_data)

            for field in pydantic_fields:
                if not field.errors:
                    pydantic_key = field.name.replace("-", "_")
                    field._data = getattr(validated_data, pydantic_key)
                    field._validated = True

        except ValidationError as e:
            for error in e.errors():
                error_field_name = error["loc"][0] if error["loc"] else None
                if error_field_name:
                    for field in pydantic_fields:
                        pydantic_key = field.name.replace("-", "_")
                        if pydantic_key == error_field_name and not field.errors:
                            msg = error["msg"]
                            msg = msg[0].upper() + msg[1:]
                            field.errors.append(msg)
                            break

        self.validated = True
        return self.is_valid
