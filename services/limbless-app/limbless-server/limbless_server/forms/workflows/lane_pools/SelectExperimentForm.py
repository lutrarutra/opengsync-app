from typing import Any, Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import FormField

from limbless_db import models

from .... import db, logger
from ...SearchBar import SearchBar
from ...HTMXFlaskForm import HTMXFlaskForm


class SelectExperimentForm(HTMXFlaskForm):
    _template_path = "forms/select-experiment-form.html"
    _form_label = "select_experiment_form"

    experiment = FormField(SearchBar, label="Select Experiment")




