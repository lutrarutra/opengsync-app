from typing import Any, Optional
from pydantic import BaseModel, ValidationError, create_model

from ..components.inputs.InputField import InputField
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

    # Class-level configuration for accordion rendering
    title: str = ""
    order: int = 0
    collapsed: bool = False
    icon: str | None = None

    def __init__(self, prefix: str = ""):
        self._prefix = prefix
        self._fields_cache: Optional[list[InputField]] = None
        self._pydantic_model: Optional[type[BaseModel]] = None

        # Clone all InputField instances to avoid shared state
        for field_name in dir(self.__class__):
            if field_name.startswith("_"):
                continue

            field = getattr(self.__class__, field_name)
            if isinstance(field, InputField):
                field_instance = self._clone_field(field)
                # Add prefix to field name for namespacing
                if prefix:
                    field_instance.name = f"{prefix}_{field.name}"
                    field_instance.id = field_instance.name
                setattr(self, field_name, field_instance)

    def _clone_field(self, field: InputField) -> InputField:
        """Clone a field instance to avoid shared state between form instances"""
        field_class = field.__class__
        new_field = object.__new__(field_class)
        # Copy all attributes except internal ones
        for key, value in field.__dict__.items():
            setattr(new_field, key, value)
        new_field.data = field.default
        new_field.errors = []
        return new_field

    @property
    def input_fields(self) -> list[InputField]:
        """Get all InputField instances in this sub-form"""
        if self._fields_cache is not None:
            return self._fields_cache

        fields = []
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, InputField):
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
            # Strip prefix when looking up data
            key = field.name
            if self._prefix and field.name.startswith(f"{self._prefix}_"):
                key = field.name[len(self._prefix) + 1 :]
            field.data = data.get(key, field.default)

    def populate_from_model(
        self, model: Any, field_mapping: dict[str, str] | None = None
    ) -> None:
        """Populate fields from a model object.

        Args:
            model: The model object to populate from
            field_mapping: Optional mapping of field_name -> model_attribute_name
        """
        for field in self.input_fields:
            # Get the model attribute name (strip prefix, use mapping if provided)
            key = field.name
            if self._prefix and field.name.startswith(f"{self._prefix}_"):
                key = field.name[len(self._prefix) + 1 :]

            if field_mapping and key in field_mapping:
                attr_name = field_mapping[key]
            else:
                attr_name = key

            value = getattr(model, attr_name, None)
            if value is not None:
                field.data = value

    def _build_pydantic_model(self) -> type[BaseModel]:
        """Dynamically build a Pydantic model from InputFields"""
        if self._pydantic_model is not None:
            return self._pydantic_model

        field_definitions = {}
        for field in self.input_fields:
            if field.required:
                default_value = ... if field.default is None else field.default
                field_definitions[field.name] = (field.pydantic_type, default_value)
            else:
                field_definitions[field.name] = (
                    field.pydantic_type | None,
                    field.default,
                )

        self._pydantic_model = create_model(
            f"{self.__class__.__name__}Model", **field_definitions
        )

        return self._pydantic_model

    def validate(self, raw_data: dict[str, Any]) -> bool:
        """Validate the sub-form data.

        Returns True if valid, False otherwise.
        Sets errors on fields that fail validation.
        """
        # Clear existing errors
        for field in self.input_fields:
            field.errors = []

        # Check required fields
        for field in self.input_fields:
            key = field.name
            if self._prefix and field.name.startswith(f"{self._prefix}_"):
                key = field.name[len(self._prefix) + 1 :]

            value = raw_data.get(key)
            if field.required and (
                value is None or (isinstance(value, str) and value.strip() == "")
            ):
                field.errors.append(f"{field.label} is required")

        # Run Pydantic validation
        PydanticModel = self._build_pydantic_model()

        try:
            # Map raw_data keys to prefixed field names
            mapped_data = {}
            for field in self.input_fields:
                key = field.name
                if self._prefix and field.name.startswith(f"{self._prefix}_"):
                    key = field.name[len(self._prefix) + 1 :]
                mapped_data[field.name] = raw_data.get(key, field.default)

            validated_data = PydanticModel(**mapped_data)

            # Update fields with validated data
            for field in self.input_fields:
                if not field.errors:
                    field.data = getattr(validated_data, field.name)

        except ValidationError as e:
            for error in e.errors():
                field_name = error["loc"][0] if error["loc"] else None
                if field_name:
                    for field in self.input_fields:
                        if field.name == field_name and not field.errors:
                            msg = error["msg"]
                            msg = msg[0].upper() + msg[1:]
                            field.errors.append(msg)
                            break

        return self.is_valid
