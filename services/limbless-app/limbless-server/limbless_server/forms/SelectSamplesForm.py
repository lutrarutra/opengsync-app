from typing import Optional

import pandas as pd
import json

from flask import Response, url_for
from wtforms import StringField

from limbless_db import models, DBSession
from limbless_db.categories import SampleStatusEnum, LibraryStatusEnum, PoolStatusEnum

from .. import db, logger
from .HTMXFlaskForm import HTMXFlaskForm


class SelectSamplesForm(HTMXFlaskForm):
    _template_path = "forms/select-samples.html"
    _form_label = "store_samples_form"

    selected_sample_ids = StringField()
    selected_library_ids = StringField()
    selected_pool_ids = StringField()

    error_dummy = StringField()

    def __init__(
        self, workflow: str, formdata: dict = {}, context: dict = {},
        select_samples: bool = True, select_libraries: bool = True, select_pools: bool = True,
        sample_status_filter: Optional[list[SampleStatusEnum]] = None,
        library_status_filter: Optional[list[LibraryStatusEnum]] = None,
        pool_status_filter: Optional[list[PoolStatusEnum]] = None,
    ):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.select_samples = select_samples
        self.select_libraries = select_libraries
        self.select_pools = select_pools

        self._context["select_samples"] = select_samples
        self._context["select_libraries"] = select_libraries
        self._context["select_pools"] = select_pools
        self._context["workflow"] = workflow
        self._context = {**self._context, **context}

        logger.debug(self._context)

        url_context = {"workflow": workflow}
        if "seq_request" in context.keys():
            url_context["seq_request_id"] = context["seq_request"].id
        if "experiment" in context.keys():
            url_context["experiment_id"] = context["experiment"].id

        self._context["post_url"] = url_for(f'{workflow}_workflow.select')  # type: ignore
        self._context["url_context"] = url_context
        self._context["sample_url_context"] = url_context.copy()
        self._context["library_url_context"] = url_context.copy()
        self._context["pool_url_context"] = url_context.copy()

        if sample_status_filter is not None:
            self._context["sample_url_context"]["status_id_in"] = json.dumps([status.id for status in sample_status_filter])
        if library_status_filter is not None:
            self._context["library_url_context"]["status_id_in"] = json.dumps([status.id for status in library_status_filter])
        if pool_status_filter is not None:
            self._context["pool_url_context"]["status_id_in"] = json.dumps([status.id for status in pool_status_filter])
        
    def validate(self) -> bool:
        validated = super().validate()

        selected_sample_ids = self.selected_sample_ids.data
        selected_library_ids = self.selected_library_ids.data
        selected_pool_ids = self.selected_pool_ids.data
        
        if not selected_pool_ids and not selected_library_ids and not selected_sample_ids:
            self.error_dummy.errors = ["Select at least one sample"]
            return False

        if selected_sample_ids:
            sample_ids = json.loads(selected_sample_ids)
        else:
            sample_ids = []

        if selected_library_ids:
            library_ids = json.loads(selected_library_ids)
        else:
            library_ids = []

        if selected_pool_ids:
            pool_ids = json.loads(selected_pool_ids)
        else:
            pool_ids = []

        if len(pool_ids) + len(library_ids) + len(sample_ids) == 0:
            self.selected_pool_ids.errors = ["Select at least one sample"]
            return False
        
        self.sample_ids = []
        try:
            for sample_id in sample_ids:
                self.sample_ids.append(int(sample_id))
        except ValueError:
            self.selected_sample_ids.errors = ["Invalid sample id"]
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
        
        self._context["selected_samples"] = self.sample_ids
        self._context["selected_libraries"] = self.library_ids
        self._context["selected_pools"] = self.pool_ids
        return validated
    
    def get_tables(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        sample_data = dict(id=[], name=[], status_id=[])
        library_data = dict(id=[], name=[], status_id=[])
        pool_data = dict(id=[], name=[], status_id=[])

        with DBSession(db) as session:
            for sample_id in self.sample_ids:
                if (sample := session.get_sample(sample_id)) is None:
                    logger.error(f"Sample {sample_id} not found")
                    raise ValueError(f"Sample {sample_id} not found")
                
                sample_data["id"].append(sample.id)
                sample_data["name"].append(sample.name)
                sample_data["status_id"].append(sample.status_id)

            for library_id in self.library_ids:
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")

                library_data["id"].append(library.id)
                library_data["name"].append(library.name)
                library_data["status_id"].append(library.status_id)

            for pool_id in self.pool_ids:
                if (pool := session.get_pool(pool_id)) is None:
                    logger.error(f"Pool {pool_id} not found")
                    raise ValueError(f"Pool {pool_id} not found")

                pool_data["id"].append(pool.id)
                pool_data["name"].append(pool.name)
                pool_data["status_id"].append(pool.status_id)

        return pd.DataFrame(sample_data), pd.DataFrame(library_data), pd.DataFrame(pool_data)