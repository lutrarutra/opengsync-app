from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, EmailField, BooleanField
from wtforms.validators import DataRequired, Length


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

    contact_person_name = StringField(
        "Contact Person Name", validators=[DataRequired(), Length(max=64)],
        description="Name of the contact person."
    )

    contact_person_email = EmailField(
        "Contact Person Email", validators=[DataRequired(), Length(max=128)],
        description="E-Mail address of primary contact."
    )
    contact_person_phone = StringField(
        "Contact Person Phone", validators=[Length(max=16)],
        description="Phone number of primary contact (optional)."
    )

    organization_name = StringField(
        "Organization Name", validators=[DataRequired(), Length(max=64)],
        description="Name of the organization."
    )
    organization_department = StringField(
        "Organization Department", validators=[Length(max=128)],
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
    billing_code = StringField(
        "Billing Code", validators=[Length(max=64)],
        description="Billing code assigned by your institution."
    )
