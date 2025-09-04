import os
from uuid_extensions import uuid7str

import pandas as pd

from flask import Response, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FieldList, FormField, IntegerField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from opengsync_db import models
from opengsync_db.categories import MediaFileType

from .... import db, logger
from ....core.RunTime import runtime
from ...HTMXFlaskForm import HTMXFlaskForm

DEFAULT_TARGET_NM = 3.0
DEFAULT_TOTAL_VOLUME_TARGET = 50.0


class SampleSubForm(FlaskForm):
    pool_id = IntegerField(validators=[DataRequired()])
    m_reads = FloatField(validators=[DataRequired()])
    dilution = StringField(validators=[OptionalValidator()])


class UnifiedLanePoolingForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/lane_pools-1.2.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    sample_sub_forms = FieldList(FormField(SampleSubForm), min_entries=1)
    target_total_volume = FloatField(validators=[DataRequired()], default=DEFAULT_TOTAL_VOLUME_TARGET)
    target_molarity = FloatField(validators=[DataRequired()], default=DEFAULT_TARGET_NM)

    def __init__(self, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self._context["enumerate"] = enumerate

    def prepare(self):
        df = db.pd.get_experiment_laned_pools(self.experiment.id)
        df["original_qubit_concentration"] = df["qubit_concentration"]
        df["dilutions"] = None

        df = df.drop(columns=["lane"]).drop_duplicates(subset=["pool_id"]).reset_index(drop=True)

        for i, (idx, row) in enumerate(df.iterrows()):
            if i > len(self.sample_sub_forms) - 1:
                self.sample_sub_forms.append_entry()

            sample_sub_form = self.sample_sub_forms[i]
            sample_sub_form.pool_id.data = row["pool_id"]
            sample_sub_form.m_reads.data = row["num_m_reads"] * self.experiment.num_lanes

            if (pool := db.pools.get(row["pool_id"])) is None:
                logger.error(f"lane_pools_workflow: Pool with id {row['pool_id']} does not exist")
                raise ValueError(f"Pool with id {row['pool_id']} does not exist")
            
            df.at[idx, "dilutions"] = [("Orig.", pool.qubit_concentration, pool.molarity, "")]
            
            for dilution in pool.dilutions:
                sample_sub_form.dilution.data = dilution.identifier
                df.at[idx, "dilutions"].append((dilution.identifier, dilution.qubit_concentration, dilution.molarity(pool), dilution.timestamp_str()))
                df.at[idx, "qubit_concentration"] = dilution.qubit_concentration
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["share"] = df["num_m_reads"] / df["num_m_reads"].sum()

        df["molarity_color"] = "cemm-green"
        df.loc[df["molarity"] < models.Pool.warning_min_molarity, "molarity_color"] = "cemm-yellow"
        df.loc[df["molarity"] > models.Pool.warning_max_molarity, "molarity_color"] = "cemm-yellow"
        df.loc[df["molarity"] < models.Pool.error_min_molarity, "molarity_color"] = "cemm-red"
        df.loc[df["molarity"] > models.Pool.error_max_molarity, "molarity_color"] = "cemm-red"

        df["pipet"] = DEFAULT_TARGET_NM / df["molarity"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET

        self._context["df"] = df
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            return self.make_response()
        
        data = {
            "lane": [],
            "pool": [],
            "lane_id": [],
            "pool_id": [],
            "num_m_reads": [],
            "qubit_concentration": [],
            "target_total_volume": [],
            "target_concentration": [],
            "avg_fragment_size": [],
            "dilution": [],
        }
        for lane in self.experiment.lanes:
            lane.target_molarity = self.target_molarity.data
            lane.total_volume_ul = self.target_total_volume.data
            db.lanes.update(lane)
            for pool_reads_form in self.sample_sub_forms:
                if (link := db.links.get_laned_pool_link(
                    experiment_id=self.experiment.id,
                    lane_num=lane.number,
                    pool_id=pool_reads_form.pool_id.data
                )) is None:
                    logger.error(f"lane_pools_workflow: Link between lane {lane.number} and pool {pool_reads_form.pool_id.data} does not exist")
                    raise ValueError(f"Link between lane {lane.number} and pool {pool_reads_form.pool_id.data} does not exist")
                
                link.num_m_reads = pool_reads_form.m_reads.data / self.experiment.num_lanes
                if not pool_reads_form.dilution.data or pool_reads_form.dilution.data == "Orig.":
                    pool_reads_form.dilution.data = "Orig."
                    link.dilution_id = None
                else:
                    if (dilution := db.pools.get_dilution(link.pool_id, pool_reads_form.dilution.data)) is None:
                        logger.error(f"lane_pools_workflow: PoolDilution with pool_id {link.pool_id} and identifier {pool_reads_form.dilution.data} does not exist")
                        raise ValueError(f"PoolDilution with pool_id '{link.pool_id}' and identifier '{pool_reads_form.dilution.data}' does not exist")
                    link.dilution_id = dilution.id
                db.links.update_laned_pool_link(link)

                data["lane"].append(lane.number)
                data["pool"].append(link.pool.name)
                data["lane_id"].append(lane.id)
                data["pool_id"].append(link.pool.id)
                data["num_m_reads"].append(link.num_m_reads)
                data["avg_fragment_size"].append(link.pool.avg_fragment_size)
                data["qubit_concentration"].append(
                    link.dilution.qubit_concentration if link.dilution else link.pool.qubit_concentration
                )
                data["target_total_volume"].append(self.target_total_volume.data)
                data["target_concentration"].append(self.target_molarity.data)
                data["dilution"].append(link.dilution.identifier if link.dilution else "Orig.")

        df = pd.DataFrame(data)
        df["share"] = df["num_m_reads"] / df["num_m_reads"].sum()
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
        df["pipet"] = df["target_concentration"] / df["molarity"] * df["share"] * df["target_total_volume"]
            
        filename = f"lane_pooling_{self.experiment.id}"
        extension = ".tsv"

        old_file = None
        for file in self.experiment.media_files:
            if file.type == MediaFileType.LANE_POOLING_TABLE:
                old_file = file
                break
            
        if old_file:
            os.remove(os.path.join(runtime.app.media_folder, old_file.path))
            db.files.delete(file_id=old_file.id)
            logger.info(f"Old file '{old_file.path}' removed.")

        _uuid = uuid7str()
        filepath = os.path.join(runtime.app.media_folder, MediaFileType.LANE_POOLING_TABLE.dir, f"{_uuid}.tsv")
        df.to_csv(filepath, sep="\t", index=False)
        size_bytes = os.stat(filepath).st_size

        db_file = db.files.create(
            name=filename,
            uuid=_uuid,
            size_bytes=size_bytes,
            type=MediaFileType.LANE_POOLING_TABLE,
            extension=extension,
            uploader_id=user.id,
            experiment_id=self.experiment.id
        )
        _ = db.comments.create(
            author_id=user.id,
            file_id=db_file.id,
            text="Added file for pooling ratios",
            experiment_id=self.experiment.id
        )

        flash("Laning Completed!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))