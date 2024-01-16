from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import DataRequired, Length
from wtforms.validators import Optional as OptionalValidator


from .. import logger, db, models
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession


class SampleForm(FlaskForm):
    name = StringField("Sample Name", validators=[DataRequired(), Length(min=6, max=64)])
    organism = IntegerField("Organism", validators=[DataRequired()])

    def custom_validate(
        self, db_handler: DBHandler, user_id: int,
        sample_id: int | None = None,
    ) -> tuple[bool, "SampleForm"]:

        validated = self.validate()
        if not validated:
            return False, self

        with DBSession(db_handler) as session:
            if (user := session.get_user(user_id)) is None:
                logger.error(f"User with id {user_id} does not exist.")
                return False, self
            
            user_samples = user.samples

            # Creating new sample
            if sample_id is None:
                if self.name.data in [sample.name for sample in user_samples]:
                    self.name.errors = ("You already have a sample with this name.",)
                    validated = False
            # Editing existing sample
            else:
                if (sample := session.get_sample(sample_id)) is None:
                    logger.error(f"Sample with id {sample_id} does not exist.")
                    return False, self
                
                for user_sample in user_samples:
                    if self.name.data == user_sample.name:
                        if sample_id != user_sample.id:
                            self.name.errors = ("You already have a sample with this name.",)
                            validated = False
                            break

        return validated, self