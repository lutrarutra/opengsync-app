from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, EmailField, BooleanField, SelectField, IntegerField, FileField
from wtforms.validators import DataRequired, Length, Email, NumberRange
from wtforms.validators import Optional as OptionalValidator
from flask_wtf.file import FileAllowed

from ..categories import SequencingType, FlowCellType


class SeqRequestForm(FlaskForm):
    name = StringField(
        "Request Name", validators=[DataRequired(), Length(min=6, max=64)],
        description="Descriptive title of the samples and experiment."
    )
    description = TextAreaField(
        "Description", validators=[Length(max=512)],
        description="""
        Summary of the broader project context relevant for the submitted samples.
        Often useful to copy and paste a few relevant sentences from a grant proposal
        or the methods section of a previous paper on the same topic."""
    )

    technology = StringField(
        "Technology", validators=[DataRequired(), Length(max=64)],
        description="List of kits used, e.g. ('10x 5-prime V2', 'Singleron sc-RNAseq', 'Illumina complete long read', etc)."
    )

    sequencing_type = SelectField(
        choices=SequencingType.as_selectable(), validators=[DataRequired()],
        default=SequencingType.PAIRED_END.value.id,
        description="Sequencing type, i.e. Single-end or Paired-end."
    )

    num_cycles_read_1 = IntegerField(
        "Number of Cycles Read 1", validators=[OptionalValidator(), NumberRange(min=1)],
        description="Number of cycles for read 1.", default=None
    )

    num_cycles_index_1 = IntegerField(
        "Number of Cycles Index 1", validators=[OptionalValidator(), NumberRange(min=1)],
        description="Number of cycles for index 1.", default=None
    )

    num_cycles_index_2 = IntegerField(
        "Number of Cycles Index 2", validators=[OptionalValidator(), NumberRange(min=1)],
        description="Number of cycles for index 2.", default=None
    )

    num_cycles_read_2 = IntegerField(
        "Number of Cycles Read 2", validators=[OptionalValidator(), NumberRange(min=1)],
        description="Number of cycles for read 2.", default=None
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
        "Special Requirements", validators=[OptionalValidator(), Length(max=512)],
        description="Special requirements such as a high percentage PhiX spike-in to increase library complexity."
    )

    sequencer = StringField(
        "Sequencer", validators=[OptionalValidator(), Length(max=64)],
        description="Sequencer to use for sequencing."
    )

    flowcell_type = SelectField(
        "Flowcell Type", validators=[OptionalValidator()],
        choices=[(-1, "-")] + FlowCellType.as_selectable(), default=-1,
        description="Type of flowcell to use for sequencing."
    )

    current_user_is_contact = BooleanField(
        "Current User is Contact", default=True,
    )

    contact_person_name = StringField(
        "Contact Person Name", validators=[DataRequired(), Length(max=64)],
        description="Name of the contact person."
    )

    contact_person_email = EmailField(
        "Contact Person Email", validators=[DataRequired(), Email(), Length(max=128)],
        description="E-Mail address of primary contact."
    )
    contact_person_phone = StringField(
        "Contact Person Phone", validators=[Length(max=16)],
        description="Phone number of primary contact (optional)."
    )

    bioinformatician_name = StringField(
        "Bioinformatician Name", validators=[Length(max=128)],
        description="Name of the bioinformatician."
    )

    bioinformatician_email = EmailField(
        "Bioinformatician Email", validators=[OptionalValidator(), Email(), Length(max=128)],
        description="E-Mail address of the bioinformatician (optional)."
    )

    bioinformatician_phone = StringField(
        "Bioinformatician Phone", validators=[Length(max=16)],
        description="Phone number of the bioinformatician (optional)."
    )

    organization_name = StringField(
        "Organization Name", validators=[DataRequired(), Length(max=64)],
        description="Name of the organization."
    )
    organization_department = StringField(
        "Organization Department", validators=[Length(max=64)],
        description="Department of the organization."
    )
    organization_address = StringField(
        "Organization Address", validators=[DataRequired(), Length(max=128)],
        description="Address of the organization."
    )

    billing_is_organization = BooleanField(
        "Billing Same as Organization", default=True,
    )
    
    billing_contact = StringField(
        "Billing Contact", validators=[DataRequired(), Length(max=64)],
        description="Name of the billing contact person, department or institution."
    )
    billing_address = StringField(
        "Billing Address", validators=[DataRequired(), Length(max=128)],
        description="Address for billing."
    )
    billing_email = EmailField(
        "Billing Email", validators=[DataRequired(), Email(), Length(max=128)],
        description="E-Mail address for billing."
    )
    billing_phone = StringField(
        "Billing Phone", validators=[Length(max=16)],
        description="Phone number for billing (optional)."
    )

    billing_code = StringField(
        "Billing Code", validators=[Length(max=64)],
        description="Billing code assigned by your institution."
    )

    def custom_validate(self) -> tuple[bool, "SeqRequestForm"]:
        validated = self.validate()
        
        if not validated:
            return False, self
        
        if self.bioinformatician_name.data:
            if not self.bioinformatician_email.data:
                self.bioinformatician_email.errors = ("Bioinformatician email is required",)
                self.bioinformatician_email.flags.required = True
                validated = False

        return validated, self