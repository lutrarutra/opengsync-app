from typing import Optional

import pandas as pd
from flask import Response
from wtforms import StringField

from limbless_db import models, DBSession

from .HTMXFlaskForm import HTMXFlaskForm
from .. import db, logger


class SelectPoolsForm(HTMXFlaskForm):
    _template_path = "forms/select-pools.html"
    _form_label = "select_pools_form"

    pool_ids = StringField()

    def __init__(self, experiment: models.Experiment, formdata: Optional[dict] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["experiment"] = experiment
        self.selected_pool_ids: list[int] = []

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if self.pool_ids.data is None:
            self.errors["pool_ids"] = ("You must select at least one pool.",)
            return False
        
        pool_ids = self.pool_ids.data.removeprefix(",").removesuffix(",").split(",")
        try:
            self.selected_pool_ids = [int(i) for i in pool_ids]
        except ValueError:
            self.errors["pool_ids"] = ("Invalid Input.",)
            return False
        
        if len(pool_ids) == 0:
            self.errors["pool_ids"] = ("You must select at least one pool.",)
            return False

        return True

    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response()
        
        libraries = dict(
            id=[],
            name=[],
            type=[],
            pool=[],
            index_1=[],
            index_2=[],
            index_3=[],
            index_4=[],
            adapter=[],
        )
        pools = dict(
            id=[],
            name=[],
            m_reads=[],
        )
        with DBSession(db) as session:
            for pool_id in self.selected_pool_ids:
                if (pool := session.get_pool(pool_id)) is None:
                    logger.error(f"Pool with id {pool_id} not found.")
                    raise Exception(f"Pool with id {pool_id} not found.")
                pools["id"].append(pool.id)
                pools["name"].append(pool.name)
                pools["m_reads"].append(pool.num_m_reads_requested)
                
                for library in pool.libraries:
                    libraries["id"].append(library.id)
                    libraries["name"].append(library.name)
                    libraries["type"].append(library.type.name)
                    libraries["pool"].append(pool.name)
                    libraries["index_1"].append(library.index_1_sequence)
                    libraries["index_2"].append(library.index_2_sequence)
                    libraries["index_3"].append(library.index_3_sequence)
                    libraries["index_4"].append(library.index_4_sequence)
                    libraries["adapter"].append(library.adapter)
        
        library_table = pd.DataFrame(libraries)
        pool_table = pd.DataFrame(pools)
        
        data: dict[str, pd.DataFrame | dict] = {
            "library_table": library_table,
            "pool_table": pool_table,
        }
        barcode_check_form = BarcodeCheckForm(self.experiment)
        context = barcode_check_form.prepare(data) | context
        return barcode_check_form.make_response(**context)