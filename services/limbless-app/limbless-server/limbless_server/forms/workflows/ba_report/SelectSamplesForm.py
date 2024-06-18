from typing import Optional, Any

import pandas as pd
import json

from flask import Response
from wtforms import StringField, IntegerField

from limbless_db import DBSession, models

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from .CompleteBAReportForm import CompleteBAReportForm


class SelectSamplesForm(HTMXFlaskForm):
    _template_path = "workflows/ba_report/bar-1.html"
    _form_label = "ba_report_form"

    selected_library_ids = StringField()
    selected_pool_ids = StringField()
    selected_lane_ids = StringField()
    experiment_id = IntegerField()

    error_dummy = StringField()

    def __init__(self, formdata: dict = {}, experiment: Optional[models.Experiment] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["url_context"] = {}
        if self.experiment is not None:
            self._context["experiment"] = experiment
            self._context["url_context"]["experiment_id"] = self.experiment.id
            self.experiment_id.data = self.experiment.id

    def validate(self) -> bool:
        validated = super().validate()

        selected_library_ids = self.selected_library_ids.data
        selected_pool_ids = self.selected_pool_ids.data
        selected_lane_ids = self.selected_lane_ids.data
        
        if not selected_pool_ids and not selected_library_ids and not selected_lane_ids:
            self.error_dummy.errors = ["Select at least one sample"]
            return False
        
        if selected_library_ids:
            library_ids = json.loads(selected_library_ids)
        else:
            library_ids = []

        if selected_pool_ids:
            pool_ids = json.loads(selected_pool_ids)
        else:
            pool_ids = []

        if selected_lane_ids:
            lane_ids = json.loads(selected_lane_ids)
        else:
            lane_ids = []
        
        if len(pool_ids) + len(library_ids) + len(lane_ids) == 0:
            self.selected_pool_ids.errors = ["Select at least one sample"]
            return False
         
        self.library_ids = []
        try:
            for library_id in library_ids:
                self.library_ids.append(int(library_id))
        except ValueError:
            self.selected_library_ids.errors = ["Invalid library id"]
            return False
        
        self.pool_ids = []
        try:
            for library_id in pool_ids:
                self.pool_ids.append(int(library_id))
        except ValueError:
            self.selected_pool_ids.errors = ["Invalid library id"]
            return False
        
        self.lane_ids = []
        try:
            for lane_id in lane_ids:
                self.lane_ids.append(int(lane_id))
        except ValueError:
            self.selected_lane_ids.errors = ["Invalid lane id"]
            return False
        
        self._context["selected_pools"] = self.pool_ids
        self._context["selected_libraries"] = self.library_ids
        self._context["selected_lanes"] = self.lane_ids
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        pool_data = dict(
            id=[],
            name=[],
            avg_fragment_size=[],
        )

        library_data = dict(
            id=[],
            name=[],
            avg_fragment_size=[],
        )

        lane_data = dict(
            id=[],
            name=[],
            avg_fragment_size=[],
        )

        with DBSession(db) as session:
            for pool_id in self.pool_ids:
                if (pool := session.get_pool(pool_id)) is None:
                    logger.error(f"Pool {pool_id} not found")
                    raise ValueError(f"Pool {pool_id} not found")
                
                pool_data["id"].append(pool.id)
                pool_data["name"].append(pool.name)
                pool_data["avg_fragment_size"].append(pool.avg_fragment_size)

            for library_id in self.library_ids:
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")

                library_data["id"].append(library.id)
                library_data["name"].append(library.name)
                library_data["avg_fragment_size"].append(library.avg_fragment_size)

            for lane_id in self.lane_ids:
                if (lane := session.get_lane(lane_id)) is None:
                    logger.error(f"Lane {lane_id} not found")
                    raise ValueError(f"Lane {lane_id} not found")
                
                lane_data["id"].append(lane.id)
                lane_data["name"].append(f"{lane.experiment.name} L{lane.number}")
                lane_data["avg_fragment_size"].append(lane.avg_fragment_size)

        complete_ba_report_form = CompleteBAReportForm()
        metadata: dict[str, Any] = {
            "workflow": "ba_report",
        }

        if self.experiment is not None:
            metadata["experiment_id"] = self.experiment.id

        complete_ba_report_form.metadata = metadata
        
        complete_ba_report_form.add_table("pool_table", pd.DataFrame(pool_data))
        complete_ba_report_form.add_table("library_table", pd.DataFrame(library_data))
        complete_ba_report_form.add_table("lane_table", pd.DataFrame(lane_data))

        complete_ba_report_form.update_data()
        complete_ba_report_form.prepare()
        return complete_ba_report_form.make_response()