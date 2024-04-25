import os
from uuid import uuid4
from pathlib import Path
from typing import Optional, Literal

import pandas as pd
import numpy as np

from flask import Response
from wtforms import StringField, FormField
from wtforms.validators import Optional as OptionalValidator, DataRequired, Length
from werkzeug.utils import secure_filename
from .BarcodeInputForm import BarcodeInputForm

from limbless_db import models, DBSession
from limbless_db.categories import LibraryStatus

from .... import logger, db
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import SearchBar
from .SelectLibrariesForm import SelectLibrariesForm


class DefinePoolForm(HTMXFlaskForm):
    _template_path = "workflows/library_pooling/pooling-1.html"
    _form_label = "library_pooling_form"

    pool_name = StringField("Pool Name", validators=[DataRequired(), Length(min=4, max=models.Pool.name.type.length)], description="Unique label to identify the pool")  # type: ignore
    contact_person = FormField(SearchBar, label="Contact Person", description="Who prepared the libraries?")

    def prepare(self, current_user: models.User):
        self.contact_person.search_bar.data = current_user.search_name()
        self.contact_person.selected.data = current_user.search_value()

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response()
        
        select_libraries_form = SelectLibrariesForm()
        select_libraries_form.metadata = dict(
            workflow="library_pooling",
            pool_name=self.pool_name.data,
            contact_person_id=self.contact_person.selected.data,
        )
        select_libraries_form.update_data()
        return select_libraries_form.make_response(**context)