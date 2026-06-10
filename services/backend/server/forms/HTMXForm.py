from abc import ABC
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError, create_model
from markupsafe import Markup

from ..components.inputs.InputField import InputField
from ..components import inputs
from ..core import templates, config, secrets, responses, exceptions as exc
from ..core.context import ctx

class HTMXForm(ABC):
    template_path: str = ""

    csrf_token = inputs.string.StringInputField("csrf_token", hidden=True)
    
    def __init__(self, request: Request):
        self.request = request
        self.raw_data: dict[str, Any] = {}
        self._context: dict[str, Any] = {}
        self._errors: dict[str, list[str]] = {}
        self._fields_cache: Optional[list[InputField]] = None
        self._pydantic_model: Optional[type[BaseModel]] = None
        
        # Initialize all InputField instances
        for field_name in dir(self.__class__):
            if field_name.startswith('_'):
                continue
            
            field = getattr(self.__class__, field_name)
            if isinstance(field, InputField):
                # Create a new instance for this form instance
                field_instance = self._clone_field(field)
                setattr(self, field_name, field_instance)
    
    def _clone_field(self, field: InputField) -> InputField:
        """Clone a field instance to avoid shared state between form instances"""
        field_class = field.__class__
        # Create a new instance with the same attributes
        new_field = object.__new__(field_class)
        new_field.__dict__.update(field.__dict__.copy())  # type: ignore
        new_field.data = field.default
        new_field.errors = []
        return new_field
    
    def _build_pydantic_model(self) -> type[BaseModel]:
        """Dynamically build a Pydantic model from InputFields"""
        if self._pydantic_model is not None:
            return self._pydantic_model
        
        # Build field definitions for Pydantic
        field_definitions = {}
        for field in self.input_fields:
            # Use ... to make field required, or use default if provided
            default_value = ... if field.default is None else field.default
            field_definitions[field.name] = (field.pydantic_type, default_value)
        
        # Create dynamic Pydantic model
        self._pydantic_model = create_model(
            f"{self.__class__.__name__}Model",
            **field_definitions
        )
        
        return self._pydantic_model
    
    async def validate(self):
        """
        Base validation - processes form data and validates using Pydantic.
        Override in subclasses for custom validation logic.
        """
        self.raw_data = dict(await self.request.form())
        
        # Populate fields with raw data and check required
        for field in self.input_fields:
            field.data = self.raw_data.get(field.name, field.default)
            field.errors = []
            if field.required:
                if field.data is None or (isinstance(field.data, str) and field.data.strip() == ""):
                    field.errors.append(f"{field.label} is required")
        
        # Build Pydantic model
        PydanticModel = self._build_pydantic_model()
        
        try:
            validated_data = PydanticModel(**self.raw_data)
            
            # Populate fields with validated data
            for field in self.input_fields:
                if not field.errors:
                    field.data = getattr(validated_data, field.name)
            
        except ValidationError as e:
            for error in e.errors():
                field_name = error['loc'][0] if error['loc'] else None
                if field_name:
                    for field in self.input_fields:
                        if field.name == field_name:
                            # Skip pydantic errors for fields that already failed required check
                            if field.errors:
                                break
                            msg = error['msg']
                            if isinstance(field, inputs.string.StringInputField):
                                msg = msg.replace("String", field.label)
                            msg = msg[0].upper() + msg[1:]
                            field.errors.append(msg)
                            break
        
        if any(field.errors for field in self.input_fields):
            raise exc.FormValidationException(self)
    
    @property
    def input_fields(self) -> list[InputField]:
        """Get all InputField instances in this form"""
        if self._fields_cache is not None:
            return self._fields_cache
        
        fields = []
        # Iterate over instance attributes, not dir()
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith('_') and isinstance(field_value, InputField):
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
    def is_valid(self) -> bool:
        """Check if form has any errors"""
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
            token = self._generate_csrf_token()
            self.csrf_token.data = token
            self._set_csrf_cookie(token)
            await self.prepare()

        return await responses.htmx_response(template=self.template_path, status=status_code, **(await self.get_context()))

    async def render_submit_button(self, post_url: str, form_id: str, target_id: str, swap: str = "outerHTML", text: str = "Submit", class_name: str = "btn-success") -> str:
        return Markup(await templates.render_template(
            "components/inputs/submit-button.html", form=self, class_name=class_name, text=text,
            post_url=post_url, form_id=form_id, target_id=target_id, swap=swap
        ))
        