import json
from typing import Optional

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms.validators import Optional as OptionalValidator, Length
from wtforms import StringField, SelectField

from limbless_db import models, DBSession
from limbless_db.categories import SampleStatus, LibraryStatus, PoolStatus

from ... import db, logger
from ..HTMXFlaskForm import HTMXFlaskForm
from ..TableDataForm import TableDataForm


class PlateSamplesForm(HTMXFlaskForm, TableDataForm):
    _template_path = "workflows/plate_samples/plate-2.html"
    _form_label = "plate_samples_form"

    plate_order = StringField()
    plate_name = StringField("Plate Name", validators=[OptionalValidator(), Length(min=3, max=models.Plate.name.type.length)])
    plate_size = SelectField("Plate Size", choices=[("12x8", "12x8"), ("24x16", "24x16")], default="12x8")

    def __init__(self, formdata: dict = {}, context: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        logger.debug(formdata.get("file_uuid"))
        TableDataForm.__init__(self, dirname="plate_samples", uuid=formdata.get("file_uuid"))
        self._context["url_context"] = {}
        if (seq_request := context.get("seq_request")) is not None:
            self._context["url_context"]["seq_request_id"] = seq_request.id
            self._context["seq_request"] = seq_request
        if (pool := context.get("pool")) is not None:
            self._context["url_context"]["pool_id"] = pool.id
            self._context["pool"] = pool
        
        self.seq_request = seq_request
        self.pool = pool
        
    def prepare(self):
        self._context["sample_table"] = self.tables["sample_table"]
        self._context["library_table"] = self.tables["library_table"]
        self._context["pool_table"] = self.tables["pool_table"]
        
    def validate(self) -> bool:
        validated = super().validate()

        if not validated:
            return False

        self.samples: list[tuple[models.Sample | models.Library | models.Pool, int]] = []
        if (plate_order := self.plate_order.data) is not None:
            if not self.plate_name.data:
                self.plate_name.errors = ["Plate name is required"]
                return False

            plate_order = json.loads(plate_order)

            num_plate_samples = 0
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

        return True
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            self.prepare()
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
                        well=plate.get_well(i)
                    )
                elif isinstance(sample, models.Library):
                    db.add_library_to_plate(
                        plate_id=plate.id,
                        library_id=sample.id,
                        well=plate.get_well(i)
                    )

        sample_table = self.tables["sample_table"]
        library_table = self.tables["library_table"]

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
                    sample.status_id = SampleStatus.PREPARED.id
                else:
                    sample.status_id = SampleStatus.STORED.id

                for library_link in sample.library_links:
                    logger.debug(f"Library {library_link.library.id} status: {library_link.library.status_id}")
                    library_link.library.status_id = LibraryStatus.PREPARING.id
                
                sample = session.update_sample(sample)

            for i, row in library_table.iterrows():
                if (library := session.get_library(row["id"])) is None:
                    logger.error(f"{self.uuid}: Library {row['id']} not found")
                    raise ValueError(f"{self.uuid}: Library {row['id']} not found")
                
                if library.is_pooled():
                    library.status_id = LibraryStatus.POOLED.id
                else:
                    library.status_id = LibraryStatus.STORED.id
                library = session.update_library(library)

        if self.pool is not None:
            self.pool.plate_id = plate.id
            self.pool.status_id = PoolStatus.STORED.id
            self.pool = db.update_pool(self.pool)

        flash("Samples added to plate", "success")

        if self.seq_request is not None:
            return make_response(redirect=url_for("seq_requests_page.seq_request_page", seq_request_id=self.seq_request.id))
        
        if self.pool is not None:
            return make_response(redirect=url_for("pools_page.pool_page", pool_id=self.pool.id))
        
        return make_response(redirect=url_for("index_page"))