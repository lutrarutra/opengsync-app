from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FieldList, FormField, TextAreaField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length, ValidationError

from ..db import db_handler

class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = StringField("Organism", validators=[DataRequired(), Length(min=1, max=64)])
    index1 = StringField("Index 1 (Barcode i7)", validators=[DataRequired()])
    index2 = StringField("Index 2 (Barcode i5)", validators=[])

    def validate_name(self, name):
        if db_handler.get_sample_by_name(name.data):
            raise ValidationError("Sample name already exists.")

class SampleSelectForm(FlaskForm):
    query_field = StringField("Search", validators=[DataRequired()])

class SampleTextForm(FlaskForm):
    text = TextAreaField("Sample Sheet (csv/tsv)", validators=[DataRequired()])

class SampleColSelectForm(FlaskForm):
    _sample_fields = [
        ("","-"),
        ("sample_name", "Sample Name"),
        ("organism", "Organism"),
        ("index1", "Index 1 (Barcode i7)"),
        ("index2", "Index 2 (Barcode i5)"),
        ("library_name", "Library Name"),
        ("library_type", "Library Type"),
    ]
    select_field = SelectField(
        choices=_sample_fields,
    )

class SampleTableForm(FlaskForm):
    fields = FieldList(FormField(SampleColSelectForm))
    text = TextAreaField(validators=[DataRequired()])