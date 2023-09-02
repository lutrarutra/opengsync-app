from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length, ValidationError

from ..db import db_handler

class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = IntegerField("Organism", validators=[DataRequired()])
    organism_search = StringField("Organism") 

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