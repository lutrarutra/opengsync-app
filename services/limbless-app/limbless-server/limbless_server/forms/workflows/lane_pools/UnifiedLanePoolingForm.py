import os
import uuid

import pandas as pd

from flask import Response, current_app, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FieldList, FormField, IntegerField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from limbless_db import models, DBSession
from limbless_db.categories import FileType

from .... import db, logger
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

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self._context["enumerate"] = enumerate

    def prepare(self, experiment: models.Experiment):
        df = db.get_experiment_laned_pools_df(experiment.id)
        df["original_qubit_concentration"] = df["qubit_concentration"]
        df["dilutions"] = None
        df["form_idx"] = None

        df = df.drop(columns=["lane"]).drop_duplicates(subset=["pool_id"]).reset_index(drop=True)

        for i, (idx, row) in enumerate(df.iterrows()):
            if i > len(self.sample_sub_forms) - 1:
                self.sample_sub_forms.append_entry()

            df.at[idx, "form_idx"] = i
            sample_sub_form = self.sample_sub_forms[i]
            sample_sub_form.pool_id.data = row["pool_id"]
            sample_sub_form.m_reads.data = row["num_m_reads_requested"]

            with DBSession(db) as session:
                if (pool := session.get_pool(row["pool_id"])) is None:
                    logger.error(f"lane_pools_workflow: Pool with id {row['pool_id']} does not exist")
                    raise ValueError(f"Pool with id {row['pool_id']} does not exist")
                
                df.at[idx, "dilutions"] = [("Orig.", pool.qubit_concentration, pool.molarity, "")]
                
                for dilution in pool.dilutions:
                    sample_sub_form.dilution.data = dilution.identifier
                    df.at[idx, "dilutions"].append((dilution.identifier, dilution.qubit_concentration, dilution.molarity(pool), dilution.timestamp_str()))
                    df.at[idx, "qubit_concentration"] = dilution.qubit_concentration
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["share"] = df["num_m_reads_requested"] / df["num_m_reads_requested"].sum()

        df["molarity_color"] = "cemm-green"
        df.loc[df["molarity"] < models.Pool.warning_min_molarity, "molarity_color"] = "cemm-yellow"
        df.loc[df["molarity"] > models.Pool.warning_max_molarity, "molarity_color"] = "cemm-yellow"
        df.loc[df["molarity"] < models.Pool.error_min_molarity, "molarity_color"] = "cemm-red"
        df.loc[df["molarity"] > models.Pool.error_max_molarity, "molarity_color"] = "cemm-red"

        df["pipet"] = DEFAULT_TARGET_NM / df["molarity"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET

        self._context["df"] = df
    
    def process_request(self, experiment: models.Experiment, user: models.User) -> Response:
        if not self.validate():
            return self.make_response(experiment=experiment)

        df = db.get_experiment_laned_pools_df(experiment.id)
        df = df.drop(columns=["lane"]).drop_duplicates(subset=["pool_id"]).reset_index(drop=True)
        df["original_qubit_concentration"] = df["qubit_concentration"].copy()
        df["dilution"] = None

        for _, pool_reads_form in enumerate(self.sample_sub_forms):
            pool_idx = df["pool_id"] == pool_reads_form.pool_id.data
            df.loc[pool_idx, "num_m_reads_requested"] = pool_reads_form.m_reads.data
            df.loc[pool_idx, "dilution"] = pool_reads_form.dilution.data if pool_reads_form.dilution.data else "Orig."  # FIXME: ?

        for (pool_id, identifier, num_m_reads_requested), _df in df.groupby(["pool_id", "dilution", "num_m_reads_requested"], dropna=False):
            if (pool := db.get_pool(int(pool_id))) is None:
                logger.error(f"lane_pools_workflow: Pool with id {pool_id} does not exist")
                raise ValueError(f"Pool with id {pool_id} does not exist")
            pool.num_m_reads_requested = float(num_m_reads_requested) if pd.notna(num_m_reads_requested) else None
            pool = db.update_pool(pool)
            if identifier == "Orig.":
                continue
            if (dilution := db.get_pool_dilution(int(pool_id), identifier)) is None:
                logger.error(f"lane_pools_workflow: PoolDilution with pool_id {pool_id} and identifier {identifier} does not exist")
                raise ValueError(f"PoolDilution with pool_id {pool_id} and identifier {identifier} does not exist")
            
            df.loc[_df.index, "qubit_concentration"] = dilution.qubit_concentration

        df["pipet"] = None
        df["share"] = None
        df["target_total_volume"] = None
        df["target_molarity"] = None
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["share"] = df["num_m_reads_requested"] / df["num_m_reads_requested"].sum()
        df["target_total_volume"] = self.target_total_volume.data
        df["target_molarity"] = self.target_molarity.data

        df["pipet"] = df["target_molarity"] / df["molarity"] * df["share"] * df["target_total_volume"]

        filename = f"lane_pooling_{experiment.id}"
        extension = ".tsv"

        old_file = None
        for file in experiment.files:
            if file.type == FileType.LANE_POOLING_TABLE:
                old_file = file
                break
            
        if old_file:
            db.delete_file(file_id=old_file.id)
            os.remove(os.path.join(current_app.config["MEDIA_FOLDER"], old_file.path))
            logger.info(f"Old file '{old_file.path}' removed.")

        _uuid = str(uuid.uuid4())
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
            experiment_id=experiment.id
        )
        _ = db.create_comment(
            author_id=user.id,
            file_id=db_file.id,
            text="Added file for pooling ratios",
            experiment_id=experiment.id
        )

        flash("Laning Completed!", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))