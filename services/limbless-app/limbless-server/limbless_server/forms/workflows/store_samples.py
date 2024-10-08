import json
from typing import Optional
from datetime import datetime

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms.validators import Optional as OptionalValidator, Length
from wtforms import StringField, SelectField

from limbless_db import models, DBSession
from limbless_db.categories import SampleStatus, LibraryStatus, PoolStatus

from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm
from ..TableDataForm import TableDataForm


class StoreSamplesForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/store_samples/store-1.html"
    _form_label = "store_samples_form"

    plate_order = StringField()
    plate_name = StringField("Plate Name", validators=[OptionalValidator(), Length(min=3, max=models.Plate.name.type.length)])
    plate_size = SelectField("Plate Size", choices=[("12x8", "12x8"), ("24x16", "24x16")], default="12x8")

    def __init__(self, formdata: dict = {}, seq_request: Optional[models.SeqRequest] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        TableDataForm.__init__(self, dirname="store_samples", uuid=formdata.get("file_uuid"))
        self._context["url_context"] = {}
        self.seq_request = seq_request
        if seq_request is not None:
            self._context["url_context"]["seq_request_id"] = seq_request.id
            self._context["seq_request"] = seq_request
        
    def prepare(self):
        self._context["sample_table"] = self.tables["sample_table"]
        self._context["library_table"] = self.tables["library_table"]
        self._context["pool_table"] = self.tables["pool_table"]
        
    def validate(self) -> bool:
        validated = super().validate()

        if not validated:
            return False

        self.samples: list[tuple[models.Sample | models.Library | models.Pool, int]] = []
        num_plate_samples = 0
        if (plate_order := self.plate_order.data) is not None:
            plate_order = json.loads(plate_order)

            for i, id in enumerate(plate_order):
                if id is None:
                    continue
                num_plate_samples += id is not None
                sample_type = id.split("-")[0]
                try:
                    sample_id = int(id.split("-")[1])
                except ValueError:
                    self.plate_order.errors = [f"Invalid sample ID: {id}"]
                    return False
                
                if sample_type == "s":
                    if (sample := db.get_sample(sample_id)) is None:
                        self.plate_order.errors = [f"Sample with ID {sample_id} does not exist"]
                        return False
                    
                    self.samples.append((sample, i))
                elif sample_type == "l":
                    if (library := db.get_library(sample_id)) is None:
                        self.plate_order.errors = [f"Library with ID {sample_id} does not exist"]
                        return False
                    
                    self.samples.append((library, i))
                elif sample_type == "p":
                    if (pool := db.get_pool(sample_id)) is None:
                        self.plate_order.errors = [f"Pool with ID {sample_id} does not exist"]
                        return False
                    
                    self.samples.append((pool, i))

        if num_plate_samples > 0 and not self.plate_name.data:
            self.plate_name.errors = ["Plate name is required"]
            return False

        return True
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.prepare()
            logger.debug(self.errors)
            return self.make_response()
        
        if self.plate_name.data is not None and len(self.samples) > 0:
            plate = db.create_plate(
                name=self.plate_name.data.strip(),
                num_cols=int(self.plate_size.data.split("x")[0]),
                num_rows=int(self.plate_size.data.split("x")[1]),
                owner_id=user.id
            )

            for sample, i in self.samples:
                if isinstance(sample, models.Sample):
                    db.add_sample_to_plate(
                        plate_id=plate.id,
                        sample_id=sample.id,
                        well_idx=i
                    )
                elif isinstance(sample, models.Library):
                    db.add_library_to_plate(
                        plate_id=plate.id,
                        library_id=sample.id,
                        well_idx=i
                    )

        sample_table = self.tables["sample_table"]
        library_table = self.tables["library_table"]
        pool_table = self.tables["pool_table"]

        with DBSession(db) as session:
            for i, row in sample_table.iterrows():
                if (sample := session.get_sample(row["id"])) is None:
                    logger.error(f"{self.uuid}: Sample {row['id']} not found")
                    raise ValueError(f"{self.uuid}: Sample {row['id']} not found")
                
                sample_prepared = True
                for library_link in sample.library_links:
                    if not library_link.library.is_pooled():
                        sample_prepared = False
                        break
                    
                if sample_prepared:
                    sample.status = SampleStatus.PREPARED
                else:
                    sample.status = SampleStatus.STORED

                sample.timestamp_stored_utc = datetime.now()

                for library_link in sample.library_links:
                    library_link.library.status = LibraryStatus.PREPARING
                
                sample = session.update_sample(sample)

            for i, row in library_table.iterrows():
                if (library := session.get_library(row["id"])) is None:
                    logger.error(f"{self.uuid}: Library {row['id']} not found")
                    raise ValueError(f"{self.uuid}: Library {row['id']} not found")
                
                if library.is_pooled():
                    library.status = LibraryStatus.POOLED
                else:
                    library.status = LibraryStatus.STORED
                
                library.timestamp_stored_utc = datetime.now()
                library = session.update_library(library)

            for i, row in pool_table.iterrows():
                if (pool := session.get_pool(row["id"])) is None:
                    logger.error(f"{self.uuid}: Pool {row['id']} not found")
                    raise ValueError(f"{self.uuid}: Pool {row['id']} not found")
                
                pool.status = PoolStatus.STORED
                pool.timestamp_stored_utc = datetime.now()
                pool = session.update_pool(pool)

        flash("Samples stored!", "success")
        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))
        
        return make_response(redirect=url_for("index_page"))