from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms_sqlalchemy.fields import QuerySelectField
from wtforms.validators import DataRequired, Length, ValidationError

class SCRNAIndexForm(FlaskForm):
    adapter = IntegerField("Adapter", validators=[DataRequired()])
    adapter_search = StringField("Adapter")

    workflow = SelectField("Workflow", choices=[])
    
