import os
import uuid

import pandas as pd

from flask import Response, current_app, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FieldList, FormField, IntegerField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from opengsync_db import models
from opengsync_db.categories import FileType

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm

DEFAULT_TARGET_NM = 3.0
DEFAULT_TOTAL_VOLUME_TARGET = 50.0


class SampleSubForm(FlaskForm):
    pool_id = IntegerField(validators=[DataRequired()])
    lane = IntegerField(validators=[DataRequired()])
    m_reads = FloatField(validators=[DataRequired()])
    dilution = StringField(validators=[OptionalValidator()])


class LaneSubForm(FlaskForm):
    lane = IntegerField(validators=[DataRequired()])
    target_total_volume = FloatField(validators=[DataRequired()], default=DEFAULT_TOTAL_VOLUME_TARGET)
    target_concentration = FloatField("Target Molarity", validators=[DataRequired()], default=DEFAULT_TARGET_NM)


class LanePoolingForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/lane_pools-1.1.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    sample_sub_forms = FieldList(FormField(SampleSubForm), min_entries=1)
    lane_sub_forms = FieldList(FormField(LaneSubForm), min_entries=1)

    def __init__(self, experiment: models.Experiment, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self._context["experiment"] = experiment
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self._context["enumerate"] = enumerate

    def prepare(self):
        df = db.get_experiment_laned_pools_df(experiment_id=self.experiment.id)
        df["dilutions"] = None
        df["sub_form_idx"] = None

        counter = 0
        for i, ((lane, lane_id), _df) in enumerate(df.groupby(["lane", "lane_id"])):
            if i > len(self.lane_sub_forms) - 1:
                self.lane_sub_forms.append_entry()
            
            lane_sub_form: LaneSubForm = self.lane_sub_forms[i]  # type: ignore
            lane_sub_form.lane.data = lane

            for idx, row in _df.iterrows():
                if counter > len(self.sample_sub_forms) - 1:
                    self.sample_sub_forms.append_entry()

                sample_sub_form = self.sample_sub_forms[counter]
                sample_sub_form.pool_id.data = row["pool_id"]
                sample_sub_form.lane.data = lane
                sample_sub_form.m_reads.data = row["num_m_reads"]
                df.at[idx, "sub_form_idx"] = counter

                if (pool := db.get_pool(row["pool_id"])) is None:
                    logger.error(f"lane_pools_workflow: Pool with id {row['pool_id']} does not exist")
                    raise ValueError(f"Pool with id {row['pool_id']} does not exist")
                
                df.at[idx, "dilutions"] = [("Orig.", pool.qubit_concentration, pool.molarity, "")]
                sample_sub_form.dilution.data = "Orig."
                
                for dilution in pool.dilutions:
                    sample_sub_form.dilution.data = dilution.identifier
                    df.at[idx, "dilutions"].append((dilution.identifier, dilution.qubit_concentration, dilution.molarity(pool), dilution.timestamp_str()))
                    df.at[idx, "qubit_concentration"] = dilution.qubit_concentration

                counter += 1
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["share"] = None
        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "share"] = _df["num_m_reads"] / _df["num_m_reads"].sum()

        df["pipet"] = DEFAULT_TARGET_NM / df["molarity"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET
        self._context["df"] = df
    
    def process_request(self, user: models.User) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()
        
        for lane_sub_form in self.lane_sub_forms:
            if (lane := db.get_experiment_lane(
                experiment_id=self.experiment.id,
                lane_num=lane_sub_form.lane.data
            )) is None:
                logger.error(f"lane_pools_workflow: Lane {lane_sub_form.lane.data} does not exist for experiment {self.experiment.id}")
                raise ValueError(f"Lane {lane_sub_form.lane.data} does not exist for experiment {self.experiment.id}")

            lane.target_molarity = lane_sub_form.target_concentration.data
            lane.total_volume_ul = lane_sub_form.target_total_volume.data
            lane = db.update_lane(lane)

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
        for pool_reads_form in self.sample_sub_forms:
            if (link := db.get_laned_pool_link(
                experiment_id=self.experiment.id,
                lane_num=pool_reads_form.lane.data,
                pool_id=pool_reads_form.pool_id.data
            )) is None:
                logger.error(f"lane_pools_workflow: No link found for lane {pool_reads_form.lane.data} and pool {pool_reads_form.pool_id.data} for experiment {self.experiment.id} in lane_pooling_form")
                raise ValueError(f"No link found for lane {pool_reads_form.lane.data} and pool {pool_reads_form.pool_id.data} for experiment {self.experiment.id}")
            
            link.num_m_reads = float(pool_reads_form.m_reads.data)
            if not pool_reads_form.dilution.data or pool_reads_form.dilution.data == "Orig.":
                link.dilution_id = None
                pool_reads_form.dilution.data = "Orig."
            else:
                if (dilution := db.get_pool_dilution(link.pool_id, pool_reads_form.dilution.data)) is None:
                    logger.error(f"lane_pools_workflow: PoolDilution with pool_id {link.pool_id} and identifier {pool_reads_form.dilution.data} does not exist")
                    raise ValueError(f"PoolDilution with pool_id '{link.pool_id}' and identifier '{pool_reads_form.dilution.data}' does not exist")
                link.dilution_id = dilution.id

            link = db.update_laned_pool_link(link)

            data["lane"].append(link.lane.number)
            data["pool"].append(link.pool.name)
            data["lane_id"].append(link.lane.id)
            data["pool_id"].append(link.pool.id)
            data["num_m_reads"].append(link.num_m_reads)
            data["avg_fragment_size"].append(link.pool.avg_fragment_size)
            data["qubit_concentration"].append(
                link.dilution.qubit_concentration if link.dilution is not None else link.pool.qubit_concentration
            )
            data["target_total_volume"].append(link.lane.total_volume_ul)
            data["target_concentration"].append(link.lane.target_molarity)
            data["dilution"].append(link.dilution.identifier if link.dilution is not None else "Orig.")
        
        df = pd.DataFrame(data)
        df["share"] = None
        for lane, _df in df.groupby(["lane", "lane_id"]):
            df.loc[_df.index, "share"] = _df["num_m_reads"].values / _df["num_m_reads"].sum()

        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000
        df["pipet"] = df["target_concentration"] / df["molarity"] * df["share"] * df["target_total_volume"]

        filename = f"lane_pooling_{self.experiment.id}"
        extension = ".tsv"

        old_file = None
        for file in self.experiment.files:
            if file.type == FileType.LANE_POOLING_TABLE:
                old_file = file
                break
            
        if old_file:
            db.delete_file(file_id=old_file.id)
            os.remove(os.path.join(current_app.config["MEDIA_FOLDER"], old_file.path))
            logger.info(f"Old file '{old_file.path}' removed.")

        _uuid = uuid.uuid4().hex
        filepath = os.path.join(current_app.config["MEDIA_FOLDER"], FileType.LANE_POOLING_TABLE.dir, f"{_uuid}.tsv")
        df.to_csv(filepath, sep="\t", index=False)
        size_bytes = os.stat(filepath).st_size

        db_file = db.create_file(
            name=filename,
            uuid=_uuid,
            size_bytes=size_bytes,
            type=FileType.LANE_POOLING_TABLE,
            extension=extension,
            uploader_id=user.id,
            experiment_id=self.experiment.id
        )
        _ = db.create_comment(
            author_id=user.id,
            file_id=db_file.id,
            text="Added file for pooling ratios",
            experiment_id=self.experiment.id
        )

        flash("Laning Completed!", "success")

        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id))