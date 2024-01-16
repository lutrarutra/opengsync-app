from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, IntegerField, BooleanField
from wtforms.validators import DataRequired, Length, Optional

from .. import logger
from ..core.DBHandler import DBHandler
from ..core.DBSession import DBSession


class SequencerForm(FlaskForm):
    name = StringField("Sequencer Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    ip_address = StringField("IP Address", validators=[
        Optional(), Length(max=128)
    ])

    def custom_validate(
        self, db_handler: DBHandler,
        sequencer_id: int | None = None,
    ) -> tuple[bool, "SequencerForm"]:
        validated = self.validate()
        if not validated:
            return False, self
        
        with DBSession(db_handler) as session:
            # editing existing sequencer
            if sequencer_id is not None:
                if (sequencer := session.get_sequencer(sequencer_id)) is None:
                    logger.error(f"Sequencer with id {sequencer_id} does not exist.")
                    return False, self
                
                if self.name.data is not None:
                    if (temp := session.get_sequencer_by_name(self.name.data)) is not None:
                        if temp.id != sequencer_id:
                            self.name.errors = ("You already have a sequencer with this name.",)
                            validated = False
                
            # creating new sequencer
            else:
                if self.name.data is not None:
                    if session.get_sequencer_by_name(self.name.data) is not None:
                        self.name.errors = ("You already have a sequencer with this name.",)
                        validated = False

        return validated, self