import json

from flask import Response, abort, url_for, flash
from flask_htmx import make_response
from wtforms import StringField

from limbless_db import models, exceptions
from limbless_db.categories import HTTPResponse

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm


class SelectPoolsForm(HTMXFlaskForm):
    _template_path = "workflows/select_experiment_pools/sp-1.html"
    _form_label = "select_pools_form"

    selected_pool_ids = StringField()

    error_dummy = StringField()

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["selected_pools"] = experiment.pools
        self._context["selected_pool_ids"] = [pool.id for pool in experiment.pools]

    def validate(self) -> bool:
        validated = super().validate()

        selected_pool_ids = self.selected_pool_ids.data
        
        if not selected_pool_ids:
            self.error_dummy.errors = ["Select at least one pool"]
            return False

        if selected_pool_ids:
            pool_ids = json.loads(selected_pool_ids)
        else:
            pool_ids = []
        
        self.pool_ids = []

        try:
            for pool_id in pool_ids:
                self.pool_ids.append(int(pool_id))
        except ValueError:
            self.selected_pool_ids.errors = ["Invalid pool id"]
            return False
        
        self._context["selected_pool_ids"] = self.pool_ids
        return validated

    def process_request(self, experiment: models.Experiment) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()
        
        current_pool_ids = [pool.id for pool in experiment.pools]
        
        try:
            for pool_id in self.pool_ids:
                if pool_id not in current_pool_ids:
                    db.link_pool_experiment(experiment_id=experiment.id, pool_id=pool_id)
            for pool_id in current_pool_ids:
                if pool_id not in self.pool_ids:
                    db.unlink_pool_experiment(experiment_id=experiment.id, pool_id=pool_id)

        except exceptions.ElementDoesNotExist as e:
            logger.error(f"select_experiment_pools_workflow: Error linking pool to experiment: {e}")
            return abort(HTTPResponse.INTERNAL_SERVER_ERROR.id)
        
        flash("Pools added to experiment!", "success")
        return make_response(
            redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id)
        )
