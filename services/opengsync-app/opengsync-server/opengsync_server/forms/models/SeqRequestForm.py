from typing import Optional, Literal

from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, EmailField, BooleanField, SelectField, IntegerField, FormField
from wtforms.validators import DataRequired, Length, Email, NumberRange
from wtforms.validators import Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import ReadType, DataDeliveryMode, SubmissionType

from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm
from ..SearchBar import OptionalSearchBar


class SeqRequestDisclaimerForm(FlaskForm):
    disclaimer = BooleanField(
        "I have read and understood the disclaimer",
        validators=[DataRequired("You must check this field.")],
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated and self.errors == {}
    
    def validate(self) -> bool:
        self._validated = super().validate() and self.disclaimer.data is True
        return self._validated


class BasicInfoSubForm(FlaskForm):
    request_name = StringField(
        "Request Name", validators=[DataRequired(), Length(min=5, max=models.SeqRequest.name.type.length)],
        description="Descriptive title of the samples and experiment."
    )
    
    group = FormField(OptionalSearchBar, label="Group", description="Group to which the request belongs.")

    request_description = TextAreaField(
        "Description", validators=[Length(max=models.SeqRequest.description.type.length)],
        description="""
        Summary of the broader project context relevant for the submitted samples.
        Often useful to copy and paste a few relevant sentences from a grant proposal
        or the methods section of a previous paper on the same topic."""
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated and self.errors == {}
    
    def validate(self) -> bool:
        self._validated = super().validate()
        return self._validated


class TechinicalInfoSubForm(FlaskForm):
    read_type = SelectField(
        choices=ReadType.as_selectable(), validators=[DataRequired()],
        default=ReadType.PAIRED_END.id,
        description="Sequencing type, i.e. Single-end or Paired-end.",
        coerce=int
    )

    submission_type = SelectField(
        "Submission Type", choices=[(-1, "")] + SubmissionType.as_selectable(inlcude_unpooled_libraries=False), validators=[DataRequired()],
        coerce=int, default=None, description="Raw Samples: We do library preparation and pooling for you."
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
        "Special Requirements", validators=[OptionalValidator(), Length(max=models.SeqRequest.special_requirements.type.length)],
        description="Special requirements such as a high percentage PhiX spike-in to increase library complexity."
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        if self.submission_type.data == -1:
            self.submission_type.errors = ("Submission type is required",)
            self._validated = False
        
        return self._validated


class DataProcessingSubForm(FlaskForm):
    data_delivery_mode_id = SelectField("Data Delivery Mode", coerce=int, validators=[OptionalValidator()], choices=DataDeliveryMode.as_selectable())
    
    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        return self._validated


class ContactSubForm(FlaskForm):
    current_user_is_contact = BooleanField("Current User is Contact", default=False)
    
    contact_person_name = StringField(
        "Contact Person Name", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],
        description="Name of the contact person."
    )

    contact_person_email = EmailField(
        "Contact Person Email", validators=[DataRequired(), Email(), Length(max=models.Contact.email.type.length)],
        description="E-Mail address of primary contact."
    )
    contact_person_phone = StringField(
        "Contact Person Phone", validators=[DataRequired(), Length(max=models.Contact.phone.type.length)],
        description="Phone number of primary contact."
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        return self._validated


class BioinformaticianSubForm(FlaskForm):
    bioinformatician_name = StringField(
        "Bioinformatician Name", validators=[Length(max=models.Contact.name.type.length)],
        description="Name of the bioinformatician."
    )

    bioinformatician_email = EmailField(
        "Bioinformatician Email", validators=[OptionalValidator(), Email(), Length(max=models.Contact.email.type.length)],
        description="E-Mail address of the bioinformatician (optional)."
    )

    bioinformatician_phone = StringField(
        "Bioinformatician Phone", validators=[Length(max=models.Contact.phone.type.length)],
        description="Phone number of the bioinformatician (optional)."
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        if self.bioinformatician_name.data and not self.bioinformatician_email.data:
            self.bioinformatician_email.errors = ("Bioinformatician email is required",)
            self._validated = False
        return self._validated


class OrganizationSubForm(FlaskForm):
    organization_name = StringField(
        "Organization Name", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],
        description="Name of the organization."
    )
    organization_address = StringField(
        "Organization Address", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],
        description="Address of the organization."
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        return self._validated


class BillingSubForm(FlaskForm):
    billing_is_organization = BooleanField("Billing Same as Organization", default=True)
    
    billing_contact = StringField(
        "Billing Contact", validators=[DataRequired(), Length(max=models.Contact.name.type.length)],
        description="Name of the billing contact person, department or institution."
    )
    billing_address = StringField(
        "Billing Address", validators=[DataRequired(), Length(max=models.Contact.address.type.length)],
        description="Address for billing."
    )
    billing_email = EmailField(
        "Billing Email", validators=[DataRequired(), Email(), Length(max=models.Contact.email.type.length)],
        description="E-Mail address for billing."
    )
    billing_phone = StringField(
        "Billing Phone", validators=[Length(max=models.Contact.phone.type.length)],
        description="Phone number for billing (optional)."
    )

    billing_code = StringField(
        "Billing Code", validators=[Length(max=models.SeqRequest.billing_code.type.length)],
        description="Billing code assigned by your institution."
    )

    def __init__(self, formdata={}, **kwargs):
        super().__init__(formdata=formdata, **kwargs)
        self._validated = False

    def is_validated(self) -> bool:
        return self._validated
    
    def validate(self) -> bool:
        self._validated = super().validate()
        return self._validated
        

class SeqRequestForm(HTMXFlaskForm):
    _template_path = "forms/seq_request/seq_request.html"
    _form_label = "seq_request_form"

    disclaimer_form: SeqRequestDisclaimerForm = FormField(SeqRequestDisclaimerForm)  # type: ignore
    basic_info_form: BasicInfoSubForm = FormField(BasicInfoSubForm)  # type: ignore
    technical_info_form: TechinicalInfoSubForm = FormField(TechinicalInfoSubForm)  # type: ignore
    data_processing_form: DataProcessingSubForm = FormField(DataProcessingSubForm)  # type: ignore
    contact_form: ContactSubForm = FormField(ContactSubForm)  # type: ignore
    bioinformatician_form: BioinformaticianSubForm = FormField(BioinformaticianSubForm)  # type: ignore
    organization_form: OrganizationSubForm = FormField(OrganizationSubForm)  # type: ignore
    billing_form: BillingSubForm = FormField(BillingSubForm)  # type: ignore

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        formdata: dict | None = None,
        current_user: Optional[models.User] = None,
        seq_request: Optional[models.SeqRequest] = None,
    ):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.form_type = form_type

        if form_type == "create" and current_user is not None and not formdata:
            self.contact_form.contact_person_name.data = current_user.name
            self.contact_form.contact_person_email.data = current_user.email
            self.contact_form.current_user_is_contact.data = True

        elif form_type == "edit" and seq_request is not None:
            self.__fill_form(seq_request)

            self._context["seq_request"] = seq_request

    def validate(self, user: models.User, seq_request: Optional[models.SeqRequest] = None) -> bool:
        if not super().validate():
            return False
        
        if self.bioinformatician_form.bioinformatician_name.data:
            if not self.bioinformatician_form.bioinformatician_email.data:
                self.bioinformatician_form.bioinformatician_email.errors = ("Bioinformatician email is required",)
                self.bioinformatician_form.bioinformatician_email.flags.required = True
                return False
            
        try:
            if SubmissionType.get(self.technical_info_form.submission_type.data) == SubmissionType.UNPOOLED_LIBRARIES and not user.is_insider():
                self.technical_info_form.submission_type.errors = ("You can only submit raw samples or pooled libraries by default.",)
                self.technical_info_form._validated = False
        except ValueError:
            logger.error(f"Invalid submission type: {self.technical_info_form.submission_type.data}")
            raise ValueError(f"Invalid submission type: {self.technical_info_form.submission_type.data}")

        user_requests, _ = db.get_seq_requests(user_id=user.id, limit=None)
        for request in user_requests:
            if seq_request is not None and seq_request.id == request.id:
                continue
            if request.name == self.basic_info_form.request_name.data:
                self.basic_info_form.request_name.errors = ("You already have a request with this name",)
                return False
        return True
    
    def __fill_form(self, seq_request: models.SeqRequest):
        self.disclaimer_form.disclaimer.data = True
        
        self.basic_info_form.request_name.data = seq_request.name
        self.basic_info_form.group.selected.data = seq_request.group_id
        self.basic_info_form.group.search_bar.data = seq_request.group.name if seq_request.group is not None else None
        self.basic_info_form.request_description.data = seq_request.description
        
        self.technical_info_form.read_length.data = seq_request.read_length
        self.technical_info_form.submission_type.data = seq_request.submission_type.id
        self.technical_info_form.num_lanes.data = seq_request.num_lanes
        self.technical_info_form.special_requirements.data = seq_request.special_requirements
        self.technical_info_form.read_type.data = seq_request.read_type.id

        self.data_processing_form.data_delivery_mode_id.data = seq_request.data_delivery_mode.id

        self.contact_form.contact_person_name.data = seq_request.contact_person.name
        self.contact_form.contact_person_email.data = seq_request.contact_person.email
        self.contact_form.contact_person_phone.data = seq_request.contact_person.phone
        
        self.contact_form.contact_person_name.data = seq_request.contact_person.name
        self.contact_form.contact_person_email.data = seq_request.contact_person.email
        self.contact_form.contact_person_phone.data = seq_request.contact_person.phone
        
        self.bioinformatician_form.bioinformatician_name.data = seq_request.bioinformatician_contact.name if seq_request.bioinformatician_contact is not None else None
        self.bioinformatician_form.bioinformatician_email.data = seq_request.bioinformatician_contact.email if seq_request.bioinformatician_contact is not None else None
        self.bioinformatician_form.bioinformatician_phone.data = seq_request.bioinformatician_contact.phone if seq_request.bioinformatician_contact is not None else None

        self.organization_form.organization_name.data = seq_request.organization_contact.name
        self.organization_form.organization_address.data = seq_request.organization_contact.address

        self.billing_form.billing_contact.data = seq_request.billing_contact.name
        self.billing_form.billing_email.data = seq_request.billing_contact.email
        self.billing_form.billing_phone.data = seq_request.billing_contact.phone
        self.billing_form.billing_address.data = seq_request.billing_contact.address
        self.billing_form.billing_code.data = seq_request.billing_code

    def __edit_existing_request(self, seq_request: models.SeqRequest) -> Response:
        seq_request.name = self.basic_info_form.request_name.data   # type: ignore
        seq_request.group_id = self.basic_info_form.group.selected.data
        seq_request.description = self.basic_info_form.request_description.data

        seq_request.read_type = ReadType.get(self.technical_info_form.read_type.data)
        seq_request.read_length = self.technical_info_form.read_length.data
        seq_request.submission_type = SubmissionType.get(self.technical_info_form.submission_type.data)
        seq_request.special_requirements = self.technical_info_form.special_requirements.data
        seq_request.num_lanes = self.technical_info_form.num_lanes.data

        seq_request.data_delivery_mode = DataDeliveryMode.get(self.data_processing_form.data_delivery_mode_id.data)

        seq_request.contact_person.name = self.contact_form.contact_person_name.data  # type: ignore
        seq_request.contact_person.email = self.contact_form.contact_person_email.data
        seq_request.contact_person.phone = self.contact_form.contact_person_phone.data.replace(" ", "") if self.contact_form.contact_person_phone.data else None

        if self.bioinformatician_form.bioinformatician_name.data:
            if seq_request.bioinformatician_contact is None:
                bioinformatician_contact = db.create_contact(
                    name=self.bioinformatician_form.bioinformatician_name.data,
                    email=self.bioinformatician_form.bioinformatician_email.data,
                    phone=self.bioinformatician_form.bioinformatician_phone.data,
                )
                seq_request.bioinformatician_contact_id = bioinformatician_contact.id
            else:
                seq_request.bioinformatician_contact.name = self.bioinformatician_form.bioinformatician_name.data
                seq_request.bioinformatician_contact.email = self.bioinformatician_form.bioinformatician_email.data
                seq_request.bioinformatician_contact.phone = self.bioinformatician_form.bioinformatician_phone.data

        seq_request.organization_contact.name = self.organization_form.organization_name.data  # type: ignore
        seq_request.organization_contact.address = self.organization_form.organization_address.data

        seq_request.billing_contact.name = self.billing_form.billing_contact.data  # type: ignore
        seq_request.billing_contact.email = self.billing_form.billing_email.data
        seq_request.billing_contact.phone = self.billing_form.billing_phone.data
        seq_request.billing_contact.address = self.billing_form.billing_address.data
        seq_request.billing_code = self.billing_form.billing_code.data

        seq_request = db.update_seq_request(seq_request)

        flash(f"Updated sequencing request '{seq_request.name}'", "success")
        logger.info(f"Updated sequencing request '{seq_request.name}'")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
        )
    
    def __create_new_request(self, user: models.User) -> Response:
        contact_person = db.create_contact(
            name=self.contact_form.contact_person_name.data,  # type: ignore
            email=self.contact_form.contact_person_email.data,
            phone=self.contact_form.contact_person_phone.data.replace(" ", "") if self.contact_form.contact_person_phone.data else None,
        )

        billing_contact = db.create_contact(
            name=self.billing_form.billing_contact.data,  # type: ignore
            email=self.billing_form.billing_email.data,
            address=self.billing_form.billing_address.data,
            phone=self.billing_form.billing_phone.data.replace(" ", "") if self.billing_form.billing_phone.data else None
        )

        organization_contact = db.create_contact(
            name=self.organization_form.organization_name.data,  # type: ignore
            address=self.organization_form.organization_address.data,
        )

        if self.bioinformatician_form.bioinformatician_name.data:
            bioinformatician = db.create_contact(
                name=self.bioinformatician_form.bioinformatician_name.data,
                email=self.bioinformatician_form.bioinformatician_email.data,
                phone=self.bioinformatician_form.bioinformatician_phone.data.replace(" ", "") if self.bioinformatician_form.bioinformatician_phone.data else None
            )
            bioinformatician_contact_id = bioinformatician.id
        else:
            bioinformatician_contact_id = None

        seq_request = db.create_seq_request(
            name=self.basic_info_form.request_name.data,  # type: ignore
            group_id=self.basic_info_form.group.selected.data,
            description=self.basic_info_form.request_description.data,
    
            data_delivery_mode=DataDeliveryMode.get(self.data_processing_form.data_delivery_mode_id.data),
            
            num_lanes=self.technical_info_form.num_lanes.data,
            read_type=ReadType.get(self.technical_info_form.read_type.data),
            submission_type=SubmissionType.get(self.technical_info_form.submission_type.data),
            read_length=self.technical_info_form.read_length.data,
            special_requirements=self.technical_info_form.special_requirements.data,
            
            requestor_id=user.id,
            contact_person_id=contact_person.id,
            billing_contact_id=billing_contact.id,
            bioinformatician_contact_id=bioinformatician_contact_id,
            organization_contact_id=organization_contact.id,
        )

        flash(f"Created new sequencing request '{seq_request.name}'", "success")
        logger.info(f"Created new sequencing request '{seq_request.name}'")

        return make_response(
            redirect=url_for("seq_requests_page.seq_request", seq_request_id=seq_request.id),
        )
    
    def process_request(self, user: models.User, seq_request: Optional[models.SeqRequest]) -> Response:
        if not self.validate(user=user, seq_request=seq_request):
            return self.make_response()
        
        if seq_request is not None:
            return self.__edit_existing_request(seq_request)
        
        return self.__create_new_request(user=user)
