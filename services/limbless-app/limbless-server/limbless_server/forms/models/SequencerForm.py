from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from limbless_db import models, DBSession
from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm


class SequencerForm(HTMXFlaskForm):
    _template_path = "forms/sequencer.html"

    name = StringField("Sequencer Name", validators=[
        DataRequired(), Length(min=6, max=64)
    ])

    ip_address = StringField("IP Address", validators=[
        OptionalValidator(), Length(max=128)
    ])

    def validate(self, sequencer: Optional[models.Sequencer]) -> bool:
        if not super().validate():
            return False
        
        with DBSession(db) as session:
            # Editing existing sequencer
            if sequencer is not None:
                if (_ := session.get_sequencer(sequencer.id)) is None:
                    logger.error(f"Sequencer with id {sequencer.id} does not exist.")
                    return False
                
                if self.name.data is not None:
                    if (temp := session.get_sequencer_by_name(self.name.data)) is not None:
                        if temp.id != sequencer.id:
                            self.name.errors = ("You already have a sequencer with this name.",)
                            return False
                
            # Creating new sequencer
            else:
                if self.name.data is not None:
                    if session.get_sequencer_by_name(self.name.data) is not None:
                        self.name.errors = ("You already have a sequencer with this name.",)
                        return False

        return True
    
    def __create_new_sequencer(self) -> Response:
        sequencer = db.create_sequencer(
            name=self.name.data,
            ip=self.ip_address.data,
        )

        flash(f"Sequencer '{sequencer.name}' created.", "success")

        return make_response(redirect=url_for("devices_page.devices_page"))
    
    def __update_existing_sequencer(self, sequencer: models.Sequencer) -> Response:
        db.update_sequencer(
            sequencer_id=sequencer.id,
            name=self.name.data,
            ip=self.ip_address.data,
        )

        flash("Sequencer updated.", "success")
        return make_response(redirect=url_for("devices_page.sequencer_page", sequencer_id=sequencer.id))
    
    def process_request(self, **context) -> Response:
        sequencer: Optional[models.Sequencer] = context.get("sequencer")
        if not self.validate(sequencer=sequencer):
            return self.make_response(**context)
        
        if sequencer is None:
            return self.__create_new_sequencer()

        return self.__update_existing_sequencer(sequencer)