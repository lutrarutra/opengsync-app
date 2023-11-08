from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, Optional


class CategoricalMappingField(FlaskForm):
    raw_category = StringField("Category", validators=[DataRequired()])
    category = IntegerField("Category", validators=[DataRequired()])


class CategoricalMappingFieldWithNewCategory(FlaskForm):
    raw_category = StringField("Category", validators=[Optional()])
    category = IntegerField("Category", validators=[Optional()])

    new_category = StringField("New", validators=[Optional()])

