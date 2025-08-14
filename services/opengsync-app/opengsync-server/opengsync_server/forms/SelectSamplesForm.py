from typing import Optional

import pandas as pd
import json

from flask import url_for
from wtforms import StringField

from opengsync_db import models
from opengsync_db.categories import (
    SampleStatusEnum, LibraryStatusEnum, PoolStatusEnum, SampleStatus, LibraryStatus, PoolStatus,
    LibraryTypeEnum
)

from .. import db, logger
from ..forms.MultiStepForm import MultiStepForm
from ..core import exceptions


workflow_settings = {
    "store_samples": dict(
        sample_status_filter=[SampleStatus.WAITING_DELIVERY],
        library_status_filter=[LibraryStatus.ACCEPTED],
        pool_status_filter=[PoolStatus.ACCEPTED],
        select_all_samples=True,
        select_all_libraries=True,
        select_samples=True,
        select_libraries=True,
        select_pools=True,
    ),
    "select_experiment_pools": dict(
        pool_status_filter=[PoolStatus.STORED],
        select_pools=True
    ),
    "reseq": dict(
        select_libraries=True,
        select_all_libraries=True
    ),
}


class SelectSamplesForm(MultiStepForm):
    _template_path = "forms/select-samples.html"
    _form_label = "select_samples_form"
    _step_name = "select_samples"

    selected_sample_ids = StringField()
    selected_library_ids = StringField()
    selected_pool_ids = StringField()
    selected_lanes_ids = StringField()

    error_dummy = StringField()

    @staticmethod
    def create_workflow_form(
        workflow: str, formdata: dict | None = None, context: dict = {},
        selected_samples: list[models.Sample] = [],
        selected_libraries: list[models.Library] = [],
        selected_pools: list[models.Pool] = [],
        selected_lanes: list[models.Lane] = [],

    ) -> "SelectSamplesForm":
        return SelectSamplesForm(
            workflow=workflow, formdata=formdata, context=context,
            selected_samples=selected_samples,
            selected_libraries=selected_libraries,
            selected_pools=selected_pools,
            selected_lanes=selected_lanes,
            **workflow_settings[workflow]
        )

    def __init__(
        self, workflow: str, formdata: dict | None = None, context: dict = {},
        select_samples: bool = False,
        select_libraries: bool = False,
        select_pools: bool = False,
        select_lanes: bool = False,
        sample_status_filter: Optional[list[SampleStatusEnum]] = None,
        library_status_filter: Optional[list[LibraryStatusEnum]] = None,
        library_type_filter: Optional[list[LibraryTypeEnum]] = None,
        pool_status_filter: Optional[list[PoolStatusEnum]] = None,
        selected_samples: list[models.Sample] = [],
        selected_libraries: list[models.Library] = [],
        selected_pools: list[models.Pool] = [],
        selected_lanes: list[models.Lane] = [],
        select_all_samples: bool = False,
        select_all_libraries: bool = False,
        uuid: str | None = None
    ):
        url_context = {"workflow": workflow}
        if "pool" in context.keys():
            url_context["pool_id"] = context["pool"].id
        if "seq_request" in context.keys():
            url_context["seq_request_id"] = context["seq_request"].id
        if "experiment" in context.keys():
            url_context["experiment_id"] = context["experiment"].id
        if "lab_prep" in context.keys():
            url_context["lab_prep_id"] = context["lab_prep"].id

        MultiStepForm.__init__(self, uuid=uuid, formdata=formdata, step_name=SelectSamplesForm._step_name, step_args=url_context, workflow=workflow)
        self.select_samples = select_samples
        self.select_libraries = select_libraries
        self.select_pools = select_pools
        self.workflow = workflow

        self._context["select_samples"] = select_samples
        self._context["select_libraries"] = select_libraries
        self._context["select_pools"] = select_pools
        self._context["select_lanes"] = select_lanes

        self._context["selected_samples_ids"] = [sample.id for sample in selected_samples]
        self._context["selected_libraries_ids"] = [library.id for library in selected_libraries]
        self._context["selected_pools_ids"] = [pool.id for pool in selected_pools]
        self._context["selected_lanes_ids"] = [lane.id for lane in selected_lanes]

        self._context["selected_samples"] = selected_samples
        self._context["selected_libraries"] = selected_libraries
        self._context["selected_pools"] = selected_pools
        self._context["selected_lanes"] = selected_lanes

        self._context["select_all_samples"] = select_all_samples
        self._context["select_all_libraries"] = select_all_libraries

        self._context["workflow"] = workflow
        self._context = {**self._context, **context}

        if "pool" in context.keys():
            self._context["context"] = f"{context['pool'].name} ({context['pool'].id})"
        if "seq_request" in context.keys():
            self._context["context"] = f"{context['seq_request'].name} ({context['seq_request'].id})"
        if "experiment" in context.keys():
            self._context["context"] = f"{context['experiment'].name} ({context['experiment'].id})"
            if workflow in ["qubit_measure", "ba_report"]:
                self._context["select_samples"] = False
                self._context["select_libraries"] = False
        if "lab_prep" in context.keys():
            self._context["context"] = f"{context['lab_prep'].name} ({context['lab_prep'].id})"

        self._context["post_url"] = url_for(f"{workflow}_workflow.select", **url_context)  # type: ignore
        self._context["url_context"] = url_context
        self._context["sample_url_context"] = url_context.copy()
        self._context["library_url_context"] = url_context.copy()
        self._context["pool_url_context"] = url_context.copy()
        self._context["lane_url_context"] = url_context.copy()

        if sample_status_filter is not None:
            self._context["sample_url_context"]["status_id_in"] = json.dumps([status.id for status in sample_status_filter])
        if library_status_filter is not None:
            self._context["library_url_context"]["status_id_in"] = json.dumps([status.id for status in library_status_filter])
        if library_type_filter is not None:
            self._context["library_url_context"]["type_id_in"] = json.dumps([library_type.id for library_type in library_type_filter])
        if pool_status_filter is not None:
            self._context["pool_url_context"]["status_id_in"] = json.dumps([status.id for status in pool_status_filter])

        self.__sample_table: pd.DataFrame | None = None
        self.__library_table: pd.DataFrame | None = None
        self.__pool_table: pd.DataFrame | None = None
        self.__lane_table: pd.DataFrame | None = None
        
    def validate(self) -> bool:
        validated = super().validate()

        selected_sample_ids = self.selected_sample_ids.data
        selected_library_ids = self.selected_library_ids.data
        selected_pool_ids = self.selected_pool_ids.data
        selected_lanes_ids = self.selected_lanes_ids.data
        
        if not selected_pool_ids and not selected_library_ids and not selected_sample_ids and not selected_lanes_ids:
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

        if selected_lanes_ids:
            lane_ids = json.loads(selected_lanes_ids)
        else:
            lane_ids = []

        if len(pool_ids) + len(library_ids) + len(sample_ids) + len(lane_ids) == 0:
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
        
        self.lane_ids = []
        try:
            for lane_id in lane_ids:
                self.lane_ids.append(int(lane_id))
        except ValueError:
            self.selected_lanes_ids.errors = ["Invalid lane id"]
            return False
        
        self._context["selected_samples"] = self.sample_ids
        self._context["selected_libraries"] = self.library_ids
        self._context["selected_pools"] = self.pool_ids
        self._context["selected_lanes"] = self.lane_ids

        if not validated:
            return False

        sample_data = dict(id=[], name=[], status_id=[])
        library_data = dict(id=[], name=[], status_id=[])
        pool_data = dict(id=[], name=[], status_id=[])
        lane_data = dict(id=[], name=[], status_id=[])

        if self.workflow == "qubit_measure":
            sample_data["qubit_concentration"] = []
            library_data["qubit_concentration"] = []
            pool_data["qubit_concentration"] = []
            lane_data["qubit_concentration"] = []

        if self.workflow == "ba_report":
            sample_data["avg_fragment_size"] = []
            library_data["avg_fragment_size"] = []
            pool_data["avg_fragment_size"] = []
            lane_data["avg_fragment_size"] = []

        for sample_id in self.sample_ids:
            if (sample := db.samples.get(sample_id)) is None:
                logger.error(f"Sample {sample_id} not found")
                raise ValueError(f"Sample {sample_id} not found")
            
            sample_data["id"].append(sample.id)
            sample_data["name"].append(sample.name)
            sample_data["status_id"].append(sample.status_id)
            if self.workflow == "qubit_measure":
                sample_data["qubit_concentration"].append(sample.qubit_concentration)
            elif self.workflow == "ba_report":
                sample_data["avg_fragment_size"].append(sample.avg_fragment_size)

        for library_id in self.library_ids:
            if (library := db.libraries.get(library_id)) is None:
                logger.error(f"Library {library_id} not found")
                raise ValueError(f"Library {library_id} not found")

            library_data["id"].append(library.id)
            library_data["name"].append(library.name)
            library_data["status_id"].append(library.status_id)
            if self.workflow == "qubit_measure":
                library_data["qubit_concentration"].append(library.qubit_concentration)
            elif self.workflow == "ba_report":
                library_data["avg_fragment_size"].append(library.avg_fragment_size)

        for pool_id in self.pool_ids:
            if (pool := db.pools.get(pool_id)) is None:
                logger.error(f"Pool {pool_id} not found")
                raise ValueError(f"Pool {pool_id} not found")

            pool_data["id"].append(pool.id)
            pool_data["name"].append(pool.name)
            pool_data["status_id"].append(pool.status_id)
            if self.workflow == "qubit_measure":
                pool_data["qubit_concentration"].append(pool.qubit_concentration)
            elif self.workflow == "ba_report":
                pool_data["avg_fragment_size"].append(pool.avg_fragment_size)

        for lane_id in self.lane_ids:
            if (lane := db.lanes.get((lane_id)) is None:
                logger.error(f"Lane {lane_id} not found")
                raise ValueError(f"Lane {lane_id} not found")

            lane_data["id"].append(lane.id)
            lane_data["name"].append(f"{lane.experiment.name}-L{lane.number}")
            lane_data["status_id"].append(None)
            if self.workflow == "qubit_measure":
                lane_data["qubit_concentration"].append(lane.original_qubit_concentration)
            elif self.workflow == "ba_report":
                lane_data["avg_fragment_size"].append(lane.avg_fragment_size)

        self.__sample_table = pd.DataFrame(sample_data).sort_values("id")
        self.__library_table = pd.DataFrame(library_data).sort_values("id")
        self.__pool_table = pd.DataFrame(pool_data).sort_values("id")
        self.__lane_table = pd.DataFrame(lane_data).sort_values("id")
        
        return True
    
    @property
    def sample_table(self) -> pd.DataFrame:
        if self.__sample_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exceptions.InternalServerErrorException("Form not validated, call .validate() first..")
        return self.__sample_table
    
    @property
    def library_table(self) -> pd.DataFrame:
        if self.__library_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exceptions.InternalServerErrorException("Form not validated, call .validate() first..")
        return self.__library_table
    
    @property
    def pool_table(self) -> pd.DataFrame:
        if self.__pool_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exceptions.InternalServerErrorException("Form not validated, call .validate() first..")
        return self.__pool_table
    
    @property
    def lane_table(self) -> pd.DataFrame:
        if self.__lane_table is None:
            logger.error("Form not validated, call .validate() first..")
            raise exceptions.InternalServerErrorException("Form not validated, call .validate() first..")
        return self.__lane_table
    
    def get_libraries(self) -> list[models.Library]:
        libraries = []
        for _, row in self.library_table.iterrows():
            if (library := db.libraries.get(int(row["id"]))) is None:
                logger.error(f"Library {library} not found in database")
                raise Exception("Library not found in database")
            libraries.append(library)

        return libraries
    
    def get_samples(self) -> list[models.Sample]:
        samples = []
        for _, row in self.sample_table.iterrows():
            if (sample := db.samples.get(int(row["id"]))) is None:
                logger.error(f"Sample {sample} not found in database")
                raise Exception("Sample not found in database")
            samples.append(sample)

        return samples
    
    def get_pools(self) -> list[models.Pool]:
        pools = []
        for _, row in self.pool_table.iterrows():
            if (pool := db.pools.get(int(row["id"]))) is None:
                logger.error(f"Pool {pool} not found in database")
                raise Exception("Pool not found in database")
            pools.append(pool)

        return pools
    
    def get_lanes(self) -> list[models.Lane]:
        lanes = []
        for _, row in self.lane_table.iterrows():
            if (lane := db.lanes.get_lane((int(row["id"]))) is None:
                logger.error(f"Lane {lane} not found in database")
                raise Exception("Lane not found in database")
            lanes.append(lane)

        return lanes