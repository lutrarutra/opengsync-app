from abc import ABC
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError, create_model
from markupsafe import Markup

from ..components.inputs.BaseInputField import BaseInputField
from ..components import inputs
from ..core import templates, config, secrets, responses, exceptions as exc
from ..core.context import ctx
from .SubHTMXForm import SubHTMXForm


class HTMXForm(ABC):
    template_path: str = ""

    csrf_token = inputs.string.StringInputField("csrf_token", hidden=True)

    def __init__(self, request: Request):
        self.request = request
        self.raw_data: dict[str, Any] = {}
        self._context: dict[str, Any] = {}
        self._fields_cache: Optional[list[BaseInputField]] = None
        self._sub_forms_cache: Optional[list[SubHTMXForm]] = None
        self._pydantic_model: Optional[type[BaseModel]] = None

        for field_name in dir(self.__class__):
            if field_name.startswith("_"):
                continue

            field = getattr(self.__class__, field_name)
            if isinstance(field, BaseInputField):
                field_instance = self._clone_field(field)
                field_instance.name = field_name
                field_instance.id = field_name
                setattr(self, field_name, field_instance)

        for field_name in dir(self.__class__):
            if field_name.startswith("_"):
                continue

            field = getattr(self.__class__, field_name)
            if isinstance(field, SubHTMXForm):
                sub_form_class = field.__class__
                sub_form_instance = sub_form_class(prefix=field_name)
                for attr_name, attr_value in field.__dict__.items():
                    if not attr_name.startswith("_") and not isinstance(attr_value, BaseInputField):
                        setattr(sub_form_instance, attr_name, attr_value)
                setattr(self, field_name, sub_form_instance)

        if self.request.method == "GET":
            token = self._generate_csrf_token()
            self.csrf_token.data = token
            self._set_csrf_cookie(token)
        else:
            self.csrf_token.data = self._get_expected_csrf_token() or ""

    def _clone_field(self, field: BaseInputField) -> BaseInputField:
        """Clone a field instance to avoid shared state between form instances"""
        field_class = field.__class__
        new_field = object.__new__(field_class)
        new_field.__dict__.update(field.__dict__.copy())  # type: ignore
        new_field._data = field.default
        new_field._validated = False
        new_field._self_validated = False
        new_field.raw_data = None
        new_field.errors = []
        return new_field

    def _build_pydantic_model(self, fields: list[BaseInputField] | None = None) -> type[BaseModel]:
        """Dynamically build a Pydantic model from InputFields"""
        if fields is None and self._pydantic_model is not None:
            return self._pydantic_model

        if fields is None:
            fields = self.input_fields

        field_definitions = {}
        for field in fields:
            if field.required:
                default_value = ... if field.default is None else field.default
                field_definitions[field.name] = (field.pydantic_type, default_value)
            else:
                field_definitions[field.name] = (
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

    async def validate(self):
        """
        Base validation - processes form data and validates using Pydantic.
        Also validates all SubHTMXForm instances.
        Override in subclasses for custom validation logic.
        """
        self.raw_data = dict(await self.request.form())

        if self.request.method != "GET":
            submitted_token = self.raw_data.get("csrf_token")
            expected_token = self._get_expected_csrf_token()
            if not submitted_token or not expected_token or submitted_token != expected_token:
                self.csrf_token.errors.append("Invalid or missing CSRF token.")
            else:
                self.csrf_token.data = submitted_token

        all_sub_forms_valid = True
        for sub_form in self.sub_forms:
            if not await sub_form.validate(self.raw_data):
                all_sub_forms_valid = False

        for field in self.input_fields:
            field.raw_data = self.raw_data.get(field.name, field.default)
            field.errors = []
            if field.required:
                if field.raw_data is None or (
                    isinstance(field.raw_data, str) and field.raw_data.strip() == ""
                ):
                    field.errors.append(f"{field.label} is required")
            else:
                if isinstance(field.raw_data, str) and field.raw_data.strip() == "":
                    field.raw_data = None
                    self.raw_data[field.name] = None

        # Fields that implement their own validate() (e.g. SpreadsheetInputField)
        # are validated here and excluded from Pydantic validation below.
        pydantic_fields = []
        for field in self.input_fields:
            if field.validate(self.raw_data):
                if not field._self_validated:
                    pydantic_fields.append(field)
            # If field.validate() returned False, errors are already recorded.

        PydanticModel = self._build_pydantic_model(pydantic_fields)

        try:
            validated_data = PydanticModel(**{
                field.name: self.raw_data.get(field.name, field.default)
                for field in pydantic_fields
            })

            for field in pydantic_fields:
                if not field.errors:
                    field._data = getattr(validated_data, field.name)
                    field._validated = True

        except ValidationError as e:
            for error in e.errors():
                field_name = error["loc"][0] if error["loc"] else None
                if field_name:
                    for field in self.input_fields:
                        if field.name == field_name:
                            if field.errors:
                                break
                            msg = error["msg"]
                            if isinstance(field, inputs.string.StringInputField):
                                msg = msg.replace("String", field.label)
                            msg = msg[0].upper() + msg[1:]
                            field.errors.append(msg)
                            break

        if not all_sub_forms_valid or any(field.errors for field in self.input_fields):
            raise exc.FormValidationException(self)

    @property
    def input_fields(self) -> list[BaseInputField]:
        """Get all direct InputField instances in this form (not from sub-forms)"""
        if self._fields_cache is not None:
            return self._fields_cache

        fields = []
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, BaseInputField):
                fields.append(field_value)

        self._fields_cache = fields
        return fields

    @property
    def sub_forms(self) -> list[SubHTMXForm]:
        """Get all SubHTMXForm instances in this form"""
        if self._sub_forms_cache is not None:
            return self._sub_forms_cache

        sub_forms = []
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, SubHTMXForm):
                sub_forms.append(field_value)

        self._sub_forms_cache = sub_forms
        return sub_forms

    @property
    def sub_form_dict(self) -> dict[str, SubHTMXForm]:
        """Get sub-forms as a dict mapping field_name to sub_form"""
        result = {}
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith("_") and isinstance(field_value, SubHTMXForm):
                result[field_name] = field_value
        return result

    def get_sub_form(self, name: str) -> SubHTMXForm | None:
        """Get a sub-form by its field name"""
        return self.sub_form_dict.get(name)

    @property
    def all_fields(self) -> list[BaseInputField]:
        """Get ALL fields including those from sub-forms"""
        fields = list(self.input_fields)
        for sub_form in self.sub_forms:
            fields.extend(sub_form.input_fields)
        return fields

    @property
    def errors(self) -> dict[str, list[str]]:
        """Get all errors from all fields and sub-forms"""
        all_errors = {}

        for field in self.input_fields:
            if field.errors:
                all_errors[field.name] = field.errors

        for sub_form in self.sub_forms:
            all_errors.update(sub_form.errors)

        return all_errors

    @property
    def is_valid(self) -> bool:
        """Check if form and all sub-forms have no errors"""
        return len(self.errors) == 0

    async def prepare(self):
        pass

    async def get_context(self) -> dict:
        return self._context | {"form": self, "request": self.request}

    def _generate_csrf_token(self) -> str:
        return secrets.url_safe_token(32)

    def _set_csrf_cookie(self, token: str) -> None:
        """Mirror the CSRF token in a cookie for double-submit validation."""
        ctx.response.set_cookie(
            key="csrf_token",
            value=token,
            max_age=config.settings.SESSION_EXPIRE_SECONDS,
            httponly=False,
            secure=not config.settings.ENVIRONMENT == "dev",
            samesite="lax",
        )

    def _get_expected_csrf_token(self) -> str | None:
        """Retrieve the expected CSRF token from the cookie."""
        return self.request.cookies.get("csrf_token")

    async def make_response(self, status_code: int = 200) -> Response:
        if self.request.method == "GET":
            await self.prepare()
        elif self.raw_data:
            for sub_form in self.sub_forms:
                sub_form.populate_from_data(self.raw_data)
            for field in self.input_fields:
                field.raw_data = self.raw_data.get(field.name, field.default)

        return await responses.htmx_response(
            template=self.template_path,
            status_code=status_code,
            **(await self.get_context()),
        )

    @property
    def csrf_token_value(self) -> str:
        if not self.csrf_token.data:
            raise ValueError("CSRF token has not been generated yet.")
        return self.csrf_token.data

    async def render_submit_button(
        self,
        post_url: str,
        form_id: str,
        target_id: str,
        swap: str = "outerHTML",
        text: str = "Submit",
        class_name: str = "btn-success",
    ) -> str:
        return Markup(
            await templates.render_template(
                "components/inputs/submit-button.html",
                form=self,
                class_name=class_name,
                text=text,
                post_url=post_url,
                form_id=form_id,
                target_id=target_id,
                swap=swap,
            )
        )
