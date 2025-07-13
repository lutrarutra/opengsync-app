from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Length, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import SequencerModel

from ... import logger, db
from ..HTMXFlaskForm import HTMXFlaskForm


class SequencerForm(HTMXFlaskForm):
    _template_path = "forms/sequencer.html"

    name = StringField("Sequencer Name", validators=[
        DataRequired(), Length(min=3, max=models.Sequencer.name.type.length)
    ])

    model = SelectField("Sequencer Model", choices=SequencerModel.as_selectable(), coerce=int)

    ip_address = StringField("IP Address", validators=[
        OptionalValidator(), Length(max=models.Sequencer.ip.type.length)
    ])

    def __init__(self, formdata: Optional[dict[str, str]] = None, sequencer: Optional[models.Sequencer] = None):
        super().__init__(formdata=formdata)
        if sequencer is not None:
            self.__fill_form(sequencer)

    def __fill_form(self, sequencer: models.Sequencer):
        self.name.data = sequencer.name
        self.model.data = sequencer.model_id
        self.ip_address.data = sequencer.ip

    def validate(self, sequencer: Optional[models.Sequencer]) -> bool:
        if not super().validate():
            return False
        
        # Editing existing sequencer
        if sequencer is not None:
            if (_ := db.get_sequencer(sequencer.id)) is None:
                logger.error(f"Sequencer with id {sequencer.id} does not exist.")
                return False
            
            if self.name.data is not None:
                if (temp := db.get_sequencer_by_name(self.name.data)) is not None:
                    if temp.id != sequencer.id:
                        self.name.errors = ("You already have a sequencer with this name.",)
                        return False
            
        # Creating new sequencer
        else:
            if self.name.data is not None:
                if db.get_sequencer_by_name(self.name.data) is not None:
                    self.name.errors = ("You already have a sequencer with this name.",)
                    return False

        return True
    
    def __create_new_sequencer(self) -> Response:
        sequencer = db.create_sequencer(
            name=self.name.data,  # type: ignore
            model=SequencerModel.get(self.model.data),
            ip=self.ip_address.data,
        )

        flash(f"Sequencer '{sequencer.name}' created.", "success")

        return make_response(redirect=url_for("devices_page.devices_page"))
    
    def __update_existing_sequencer(self, sequencer: models.Sequencer) -> Response:
        sequencer.name = self.name.data  # type: ignore
        sequencer.ip = self.ip_address.data
        sequencer.model = SequencerModel.get(self.model.data)
        sequencer = db.update_sequencer(sequencer)

        flash("Sequencer updated.", "success")
        return make_response(redirect=url_for("devices_page.sequencer_page", sequencer_id=sequencer.id))
    
    def process_request(self, **context) -> Response:
        sequencer: Optional[models.Sequencer] = context.get("sequencer")
        if not self.validate(sequencer=sequencer):
            return self.make_response(**context)
        
        if sequencer is None:
            return self.__create_new_sequencer()

        return self.__update_existing_sequencer(sequencer)