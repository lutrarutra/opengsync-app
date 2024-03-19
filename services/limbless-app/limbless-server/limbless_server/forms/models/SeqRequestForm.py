from typing import Optional, Any

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, TextAreaField, EmailField, BooleanField, SelectField, IntegerField
from wtforms.validators import DataRequired, Length, Email, NumberRange
from wtforms.validators import Optional as OptionalValidator

from limbless_db import models
from limbless_db.categories import ReadType, DataDeliveryMode
from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm


class SeqRequestForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/seq_request.html"
    _form_label = "seq_request_form"

    name = StringField(
        "Request Name", validators=[DataRequired(), Length(min=6, max=models.SeqRequest.name.type.length)],  # type: ignore
        description="Descriptive title of the samples and experiment."
    )
    description = TextAreaField(
        "Description", validators=[Length(max=models.SeqRequest.description.type.length)],  # type: ignore
        description="""
        Summary of the broader project context relevant for the submitted samples.
        Often useful to copy and paste a few relevant sentences from a grant proposal
        or the methods section of a previous paper on the same topic."""
    )

    data_delivery_mode_id = SelectField("Data Delivery Mode", coerce=int, validators=[OptionalValidator()], choices=DataDeliveryMode.as_selectable())

    sequencing_type = SelectField(
        choices=ReadType.as_selectable(), validators=[DataRequired()],
        default=ReadType.PAIRED_END.id,
        description="Sequencing type, i.e. Single-end or Paired-end.",
        coerce=int
    )

    read_length = IntegerField(
        "Read Length", validators=[OptionalValidator(), NumberRange(min=1)],
        description="Read length.", default=None
    )

    num_lanes = IntegerField(
        "Number of Lanes", validators=[OptionalValidator(), NumberRange(min=1, max=8)],
        description="Number of lanes.", default=None
    )

    special_requirements = TextAreaField(
        "Special Requirements", validators=[OptionalValidator(), Length(max=models.SeqRequest.special_requirements.type.length)],  # type: ignore
        description="Special requirements such as a high percentage PhiX spike-in to increase library complexity."
    )

    current_user_is_contact = BooleanField(
        "Current User is Contact", default=True,
    )

    contact_person_name = StringField(
        "Contact Person Name", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],  # type: ignore
        description="Name of the contact person."
    )

    contact_person_email = EmailField(
        "Contact Person Email", validators=[DataRequired(), Email(), Length(max=models.Contact.email.type.length)],  # type: ignore
        description="E-Mail address of primary contact."
    )
    contact_person_phone = StringField(
        "Contact Person Phone", validators=[Length(max=models.Contact.phone.type.length)],  # type: ignore
        description="Phone number of primary contact (optional)."
    )

    bioinformatician_name = StringField(
        "Bioinformatician Name", validators=[Length(max=models.Contact.name.type.length)],  # type: ignore
        description="Name of the bioinformatician."
    )

    bioinformatician_email = EmailField(
        "Bioinformatician Email", validators=[OptionalValidator(), Email(), Length(max=models.Contact.email.type.length)],  # type: ignore
        description="E-Mail address of the bioinformatician (optional)."
    )

    bioinformatician_phone = StringField(
        "Bioinformatician Phone", validators=[Length(max=models.Contact.phone.type.length)],  # type: ignore
        description="Phone number of the bioinformatician (optional)."
    )

    organization_name = StringField(
        "Organization Name", validators=[DataRequired(), Length(max=models.SeqRequest.organization_name.type.length)],  # type: ignore
        description="Name of the organization."
    )
    organization_department = StringField(
        "Organization Department", validators=[Length(max=models.SeqRequest.organization_department.type.length)],  # type: ignore
        description="Department of the organization."
    )
    organization_address = StringField(
        "Organization Address", validators=[DataRequired(), Length(max=models.SeqRequest.organization_address.type.length)],  # type: ignore
        description="Address of the organization."
    )

    billing_is_organization = BooleanField(
        "Billing Same as Organization", default=True,
    )
    
    billing_contact = StringField(
        "Billing Contact", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],  # type: ignore
        description="Name of the billing contact person, department or institution."
    )
    billing_address = StringField(
        "Billing Address", validators=[DataRequired(), Length(max=models.Contact.address.type.length)],  # type: ignore
        description="Address for billing."
    )
    billing_email = EmailField(
        "Billing Email", validators=[DataRequired(), Email(), Length(max=models.Contact.email.type.length)],  # type: ignore
        description="E-Mail address for billing."
    )
    billing_phone = StringField(
        "Billing Phone", validators=[Length(max=models.Contact.phone.type.length)],  # type: ignore
        description="Phone number for billing (optional)."
    )

    billing_code = StringField(
        "Billing Code", validators=[Length(max=models.SeqRequest.billing_code.type.length)],  # type: ignore
        description="Billing code assigned by your institution."
    )

    def __init__(self, formdata: Optional[dict[str, Any]] = None, seq_request: Optional[models.SeqRequest] = None):
        super().__init__(formdata=formdata)
        if seq_request is not None:
            self.__fill_form(seq_request)

    def validate(self, user_id: int, seq_request: Optional[models.SeqRequest] = None) -> bool:
        if not super().validate():
            return False
        
        if self.bioinformatician_name.data:
            if not self.bioinformatician_email.data:
                self.bioinformatician_email.errors = ("Bioinformatician email is required",)
                self.bioinformatician_email.flags.required = True
                return False

        user_requests, _ = db.get_seq_requests(user_id=user_id, limit=None)

        if seq_request is not None:
            for request in user_requests:
                if seq_request.id == request.id:
                    continue
                if request.name == self.name.data:
                    self.name.errors = ("You already have a request with this name",)
                    return False
        return True
    
    def __fill_form(self, seq_request: models.SeqRequest):
        self.current_user_is_contact.data = False
        self.billing_is_organization.data = False
        self.name.data = seq_request.name
        self.description.data = seq_request.description
        self.read_length.data = seq_request.read_length
        self.num_lanes.data = seq_request.num_lanes
        self.special_requirements.data = seq_request.special_requirements
        self.sequencing_type.data = seq_request.sequencing_type.id
        self.contact_person_name.data = seq_request.contact_person.name
        self.contact_person_email.data = seq_request.contact_person.email
        self.contact_person_phone.data = seq_request.contact_person.phone
        self.organization_name.data = seq_request.organization_name
        self.organization_department.data = seq_request.organization_department
        self.organization_address.data = seq_request.organization_address
        self.billing_contact.data = seq_request.billing_contact.name
        self.billing_email.data = seq_request.billing_contact.email
        self.billing_phone.data = seq_request.billing_contact.phone
        self.billing_address.data = seq_request.billing_contact.address
        self.billing_code.data = seq_request.billing_code
        self.bioinformatician_name.data = seq_request.bioinformatician_contact.name if seq_request.bioinformatician_contact is not None else None
        self.bioinformatician_email.data = seq_request.bioinformatician_contact.email if seq_request.bioinformatician_contact is not None else None
        self.bioinformatician_phone.data = seq_request.bioinformatician_contact.phone if seq_request.bioinformatician_contact is not None else None
    
    def __edit_existing_request(self, seq_request: models.SeqRequest) -> Response:
        db.update_contact(
            seq_request.billing_contact_id,
            name=self.billing_contact.data,
            email=self.billing_email.data,
            phone=self.billing_phone.data,
            address=self.billing_address.data,
        )

        db.update_contact(
            seq_request.contact_person_id,
            name=self.contact_person_name.data,
            phone=self.contact_person_phone.data,
            email=self.contact_person_email.data,
        )

        if self.bioinformatician_name.data:
            if (bioinformatician_contact := seq_request.bioinformatician_contact) is None:
                bioinformatician_contact = db.create_contact(
                    name=self.bioinformatician_name.data,
                    email=self.bioinformatician_email.data,
                    phone=self.bioinformatician_phone.data,
                )
            else:
                db.update_contact(
                    bioinformatician_contact.id,
                    name=self.bioinformatician_name.data,
                    email=self.bioinformatician_email.data,
                    phone=self.bioinformatician_phone.data,
                )

        seq_request.name = self.name.data   # type: ignore
        seq_request.description = self.description.data
        seq_request.sequencing_type_id = ReadType.get(self.sequencing_type.data).id
        seq_request.data_delivery_mode_id = DataDeliveryMode.get(self.data_delivery_mode_id.data).id
        seq_request.read_length = self.read_length.data
        seq_request.special_requirements = self.special_requirements.data
        seq_request.num_lanes = self.num_lanes.data
        seq_request.billing_code = self.billing_code.data
        seq_request.organization_name = self.organization_name.data  # type: ignore
        seq_request.organization_department = self.organization_department.data
        seq_request.organization_address = self.organization_address.data  # type: ignore

        seq_request = db.update_seq_request(seq_request)

        flash(f"Updated sequencing request '{seq_request.name}'", "success")
        logger.info(f"Updated sequencing request '{seq_request.name}'")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
        )
    
    def __create_new_request(self, user_id: int) -> Response:
        contact_person = db.create_contact(
            name=self.contact_person_name.data,  # type: ignore
            email=self.contact_person_email.data,
            phone=self.contact_person_phone.data,
        )

        billing_contact = db.create_contact(
            name=self.billing_contact.data,  # type: ignore
            email=self.billing_email.data,
            address=self.billing_address.data,
            phone=self.billing_phone.data,
        )

        # Create bioinformatician contact if needed
        if self.bioinformatician_name.data:
            bioinformatician = db.create_contact(
                name=self.bioinformatician_name.data,
                email=self.bioinformatician_email.data,
                phone=self.bioinformatician_phone.data,
            )
            bioinformatician_contact_id = bioinformatician.id
        else:
            bioinformatician_contact_id = None

        seq_request = db.create_seq_request(
            name=self.name.data,  # type: ignore
            description=self.description.data,
            requestor_id=user_id,
            contact_person_id=contact_person.id,
            billing_contact_id=billing_contact.id,
            bioinformatician_contact_id=bioinformatician_contact_id,
            seq_type=ReadType.get(self.sequencing_type.data),
            data_delivery_mode=DataDeliveryMode.get(self.data_delivery_mode_id.data),
            read_length=self.read_length.data,
            special_requirements=self.special_requirements.data,
            num_lanes=self.num_lanes.data,
            organization_name=self.organization_name.data,  # type: ignore
            organization_address=self.organization_address.data,  # type: ignore
            organization_department=self.organization_department.data,
        )

        flash(f"Created new sequencing request '{seq_request.name}'", "success")
        logger.info(f"Created new sequencing request '{seq_request.name}'")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=seq_request.id),
        )
    
    def process_request(self, **context) -> Response:
        user_id = context["user_id"]
        seq_request: Optional[models.SeqRequest] = context.get("seq_request")

        if not self.validate(user_id=user_id, seq_request=seq_request):
            return self.make_response(**context)
        
        if seq_request is not None:
            return self.__edit_existing_request(seq_request)
        
        return self.__create_new_request(user_id=user_id)
