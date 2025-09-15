from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import Optional as OptionalValidator, DataRequired


class SearchBar(FlaskForm):
    search_bar = StringField(validators=[OptionalValidator()], default="", name="search")
    selected = IntegerField(validators=[DataRequired()], default=None)
    optional = False


class OptionalSearchBar(FlaskForm):
    search_bar = StringField(validators=[OptionalValidator()], default="", name="search")
    selected = IntegerField(validators=[OptionalValidator()], default=None)
    optional = True