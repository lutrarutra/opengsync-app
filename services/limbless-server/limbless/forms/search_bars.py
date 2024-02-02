from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import Optional as OptionalValidator


class OrganismSearchBar(FlaskForm):
    query_url = "/api/organism/query"

    search_bar = StringField("Select Organism", validators=[OptionalValidator()], default="")
    selected = IntegerField(validators=[OptionalValidator()], default=None)


class ProjectSearchBar(FlaskForm):
    query_url = "/api/projects/query"

    search_bar = StringField("Select Project", validators=[OptionalValidator()], default="")
    selected = IntegerField(validators=[OptionalValidator()], default=None)