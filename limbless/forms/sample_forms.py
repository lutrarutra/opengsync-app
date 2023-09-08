from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length


class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = IntegerField("Organism", validators=[DataRequired()])
    organism_search = StringField("Organism")


class SampleSelectForm(FlaskForm):
    query_field = StringField("Search", validators=[DataRequired()])


class SampleTableConfirmForm(FlaskForm):
    data = TextAreaField(validators=[DataRequired()])
    selected_samples = StringField()


class SampleColSelectForm(FlaskForm):
    _sample_fields = [
        ("", "-"),
        ("sample_name", "Sample Name"),
        ("organism", "Organism"),
    ]
    select_field = SelectField(
        choices=_sample_fields,
    )


class SampleTableForm(FlaskForm):
    fields = FieldList(FormField(SampleColSelectForm))
    data = TextAreaField(validators=[DataRequired()])
