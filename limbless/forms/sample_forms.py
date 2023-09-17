from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, FieldList, FormField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Length

from .. import logger
from ..core.DBHandler import DBHandler

class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = IntegerField("Organism", validators=[DataRequired()])

    def custom_validate(
        self,
        db_handler: DBHandler, user_id: int,
        sample_id: int | None = None,
    ) -> tuple[bool, "SampleForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        db_handler.open_session()
        if (user := db_handler.get_user(user_id)) is None:
            logger.error(f"User with id {user_id} does not exist.")
            db_handler.close_session()
            return False, self

        user_samples = user.samples

        # Creating new sample
        if sample_id is None:
            if self.name.data in [project.name for project in user_projects]:
                self.name.errors = ("You already have a project with this name.",)
                validated = False

        # Editing existing project
        else:
            for project in user_projects:
                if project.name == self.name.data:
                    if project.id != project_id and project.owner_id == user_id:
                        self.name.errors = ("You already have a library with this name.",)
                        validated = False

        db_handler.close_session()

        return validated, self


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
