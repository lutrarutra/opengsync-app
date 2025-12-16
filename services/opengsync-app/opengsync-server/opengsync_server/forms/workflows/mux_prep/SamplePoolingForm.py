from flask import Response, url_for, flash
from flask_htmx import make_response

from opengsync_db import models, exceptions

from .... import logger, tools, db  # noqa F401
from ....tools import utils
from ....tools.spread_sheet_components import TextColumn, IntegerColumn
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SpreadsheetInput import SpreadsheetInput


class SamplePoolingForm(HTMXFlaskForm):
    _template_path = "workflows/mux_prep/mux_prep-sample-pooling.html"
    _workflow_name = "mux_prep"
    _step_name = "sample_pooling"

    columns = [
        IntegerColumn("sample_id", "Sample ID", 100, required=True, read_only=True),
        TextColumn("sample_name", "Sample Name", 300, required=True, read_only=True),
        TextColumn("sample_pool", "Pool", 300, required=True, read_only=False),
    ]

    def __init__(self, lab_prep: models.LabPrep, formdata: dict | None = None):
        HTMXFlaskForm.__init__(
            self, formdata=formdata, workflow=SamplePoolingForm._workflow_name,
            step_name=SamplePoolingForm._step_name, step_args={}
        )
        self.lab_prep = lab_prep
        self._context["lab_prep"] = self.lab_prep

        sample_table = db.pd.get_lab_prep_pooling_table(self.lab_prep.id)
        self.sample_table = sample_table[sample_table["mux_type"].notna()]
        self.mux_table = self.sample_table[["sample_id", "sample_name", "sample_pool"]].drop_duplicates()

        self.spreadsheet = SpreadsheetInput(
            columns=self.columns,
            csrf_token=self._csrf_token,
            post_url=url_for("mux_prep_workflow.sample_pooling", lab_prep_id=self.lab_prep.id),
            formdata=formdata,
            df=self.mux_table
        )

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if not self.spreadsheet.validate():
            return False

        self.df = self.spreadsheet.df
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()

        self.sample_table["new_sample_pool"] = utils.map_columns(self.sample_table, self.df, "sample_id", "sample_pool")

        old_libraries: dict[int, models.Library] = dict()

        for library_id in self.sample_table["library_id"].unique():
            if (library := db.libraries.get(int(library_id))) is None:
                logger.error(f"Library {library_id} not found.")
                raise exceptions.ElementDoesNotExist(f"Library {library_id} not found.")
            
            old_libraries[library.id] = library
            library.sample_links.clear()
            db.libraries.update(library)
            db.flush()
            db.refresh(library)
        
        libraries: dict[str, models.Library] = dict()

        for (new_sample_pool, library_id), _df in self.sample_table.groupby(["new_sample_pool", "library_id"]):
            old_library = old_libraries[int(library_id)]
            library_name = f"{new_sample_pool}_{old_library.type.identifier}"
            if (new_library := libraries.get(library_name)) is None:
                new_library = db.libraries.create(
                    name=library_name,
                    sample_name=new_sample_pool,
                    library_type=old_library.type,
                    status=old_library.status,
                    owner_id=old_library.owner_id,
                    seq_request_id=old_library.seq_request_id,
                    lab_prep_id=self.lab_prep.id,
                    genome_ref=old_library.genome_ref,
                    service_type=old_library.service_type,
                    mux_type=old_library.mux_type,
                    nuclei_isolation=old_library.nuclei_isolation,
                    index_type=old_library.index_type,
                    original_library_id=old_library.original_library_id if old_library.original_library_id is not None else None,
                )
                libraries[library_name] = new_library

            new_library.features = old_library.features
            db.libraries.update(new_library)

            for _, row in _df.iterrows():
                if (sample := db.samples.get(int(row["sample_id"]))) is None:
                    logger.error(f"Sample {row['sample_id']} not found.")
                    raise Exception(f"Sample {row['sample_id']} not found.")

                db.links.link_sample_library(
                    sample_id=sample.id,
                    library_id=new_library.id,
                    mux=row["mux"],
                )

        db.flush()
        db.refresh(self.lab_prep)
        for library in self.lab_prep.libraries:
            db.refresh(library)
            if len(library.sample_links) == 0:
                db.libraries.delete(library)

        flash("Sample pool annotation processed successfully.", "success")
        return make_response(redirect=url_for("lab_preps_page.lab_prep", lab_prep_id=self.lab_prep.id))