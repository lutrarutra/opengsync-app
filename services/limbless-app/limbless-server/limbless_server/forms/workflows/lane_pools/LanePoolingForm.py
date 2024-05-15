import os
import uuid

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
    lane = IntegerField(validators=[DataRequired()])
    m_reads = FloatField(validators=[DataRequired()])
    dilution = StringField(validators=[OptionalValidator()])


class LaneSubForm(FlaskForm):
    target_total_volume = FloatField(validators=[DataRequired()], default=DEFAULT_TOTAL_VOLUME_TARGET)
    target_concentration = FloatField("Target Molarity", validators=[DataRequired()], default=DEFAULT_TARGET_NM)


class LanePoolingForm(HTMXFlaskForm):
    _template_path = "workflows/experiment/lane_pools-1.1.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    sample_sub_forms = FieldList(FormField(SampleSubForm), min_entries=1)
    lane_sub_forms = FieldList(FormField(LaneSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self._context["warning_min"] = models.Pool.warning_min_molarity
        self._context["warning_max"] = models.Pool.warning_max_molarity
        self._context["error_min"] = models.Pool.error_min_molarity
        self._context["error_max"] = models.Pool.error_max_molarity
        self._context["enumerate"] = enumerate

    def prepare(self, experiment: models.Experiment):
        df = db.get_experiment_laned_pools_df(experiment.id)
        df["original_qubit_concentration"] = df["qubit_concentration"].copy()
        df["dilutions"] = None
        df["form_idx"] = None

        counter = 0
        for i, (lane, _df) in enumerate(df.groupby("lane")):
            if i > len(self.lane_sub_forms) - 1:
                self.lane_sub_forms.append_entry()

            for idx, row in _df.iterrows():
                if counter > len(self.sample_sub_forms) - 1:
                    self.sample_sub_forms.append_entry()

                df.at[idx, "form_idx"] = counter
                sample_sub_form = self.sample_sub_forms[counter]
                sample_sub_form.pool_id.data = row["pool_id"]
                sample_sub_form.lane.data = lane
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

                counter += 1
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        df["share"] = None
        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "share"] = _df["num_m_reads_requested"] / _df["num_m_reads_requested"].sum()

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
        df["original_qubit_concentration"] = df["qubit_concentration"].copy()
        df["dilution"] = None

        for _, pool_reads_form in enumerate(self.sample_sub_forms):
            pool_idx = df["pool_id"] == pool_reads_form.pool_id.data
            lane_idx = df["lane"] == pool_reads_form.lane.data
            df.loc[pool_idx & lane_idx, "num_m_reads_requested"] = pool_reads_form.m_reads.data
            df.loc[pool_idx & lane_idx, "dilution"] = pool_reads_form.dilution.data

        for (pool_id, lane, identifier), _df in df.groupby(["pool_id", "lane", "dilution"]):
            if identifier == "Orig.":
                continue
            if (dilution := db.get_pool_dilution(int(pool_id), identifier)) is None:
                logger.error(f"lane_pools_workflow: PoolDilution with pool_id {pool_id} and identifier {identifier} does not exist")
                raise ValueError(f"PoolDilution with pool_id {pool_id} and identifier {identifier} does not exist")
            
            df.loc[_df.index, "qubit_concentration"] = dilution.qubit_concentration

        data = []
        for i, lane_target_form in enumerate(self.lane_sub_forms):
            data.append({
                "target_total_volume": lane_target_form.target_total_volume.data,
                "target_concentration": lane_target_form.target_concentration.data,
            })

        df["pipet"] = None
        df["share"] = None
        df["target_total_volume"] = None
        df["target_concentration"] = None
        df["molarity"] = df["qubit_concentration"] / (df["avg_fragment_size"] * 660) * 1_000_000

        for lane, _df in df.groupby("lane"):
            target = data[lane - 1]  # type: ignore
            df.loc[_df.index, "share"] = _df["num_m_reads_requested"] / _df["num_m_reads_requested"].sum()
            df.loc[_df.index, "target_total_volume"] = target["target_total_volume"]
            df.loc[_df.index, "target_concentration"] = target["target_concentration"]

        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "pipet"] = _df["target_concentration"] / _df["molarity"] * _df["share"] * _df["target_total_volume"]

        filename = f"lane_pooling_{experiment.id}"
        extension = ".tsv"

        old_file = None
        for file in experiment.files:
            if file.type == FileType.LANE_POOLING_TABLE:
                old_file = file
                break
            
        if old_file:
            db.remove_file_from_experiment(experiment_id=experiment.id, file_id=old_file.id)
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
        )
        comment = db.create_comment(
            author_id=user.id,
            file_id=db_file.id,
            text="Added file for pooling ratios"
        )
        db.add_experiment_comment(
            experiment_id=experiment.id,
            comment_id=comment.id
        )

        db.add_file_to_experiment(experiment.id, db_file.id)

        logger.debug(f"File '{db_file.path}' uploaded by user '{user.id}'.")
        flash("Laning Completed!", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))