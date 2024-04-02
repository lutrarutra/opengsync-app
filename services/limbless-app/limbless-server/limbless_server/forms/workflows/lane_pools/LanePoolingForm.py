import os

from flask import Response, current_app, flash, url_for
from flask_htmx import make_response
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, FieldList, FormField
from wtforms.validators import Optional as OptionalValidator, DataRequired

from limbless_db import models
from limbless_db.categories import FileType, ExperimentStatus

from .... import db, logger
from ....tools import io as iot
from ...HTMXFlaskForm import HTMXFlaskForm

DEFAULT_TARGET_NM = 3.0
DEFAULT_TOTAL_VOLUME_TARGET = 50.0


class PoolReadsSubForm(FlaskForm):
    m_reads = FloatField(validators=[DataRequired()])


class LaneTargetSubForm(FlaskForm):
    target_total_volume = FloatField(validators=[DataRequired()], default=DEFAULT_TOTAL_VOLUME_TARGET)
    target_concentration = FloatField(validators=[DataRequired()], default=DEFAULT_TARGET_NM)


class LanePoolingForm(HTMXFlaskForm):
    _template_path = "workflows/lane_pools/lp-1.html"
    _form_label = "lane_pooling_form"

    spreadsheet_dummy = StringField(validators=[OptionalValidator()])
    pool_reads_forms = FieldList(FormField(PoolReadsSubForm), min_entries=1)
    lane_target_forms = FieldList(FormField(LaneTargetSubForm), min_entries=1)

    def __init__(self, formdata: dict = {}):
        HTMXFlaskForm.__init__(self, formdata=formdata)

    def prepare(self, experiment_id: int) -> dict:
        df = db.get_experiment_lanes_df(experiment_id)

        for i, _ in enumerate(df["lane"].unique()):
            if i > len(self.lane_target_forms) - 1:
                self.lane_target_forms.append_entry()

        for i, (_, row) in enumerate(df.iterrows()):
            if i > len(self.pool_reads_forms) - 1:
                self.pool_reads_forms.append_entry()

            entry = self.pool_reads_forms[i]
            entry.m_reads.data = row["num_m_reads_requested"]
        
        # https://knowledge.illumina.com/library-preparation/dna-library-prep/library-preparation-dna-library-prep-reference_material-list/000001240
        df["total_conc"] = df["qubit_concentration"] / (df["avg_library_size"] * 660) * 1_000_000

        df["share"] = None
        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "share"] = _df["num_m_reads_requested"] / _df["num_m_reads_requested"].sum()

        df["total_conc_color"] = "cemm-green"
        df.loc[df["total_conc"] < models.Pool.warning_min_concentration, "total_conc_color"] = "cemm-yellow"
        df.loc[df["total_conc"] > models.Pool.warning_max_concentration, "total_conc_color"] = "cemm-yellow"
        df.loc[df["total_conc"] < models.Pool.error_min_concentration, "total_conc_color"] = "cemm-red"
        df.loc[df["total_conc"] > models.Pool.error_max_concentration, "total_conc_color"] = "cemm-red"

        df["pipet"] = DEFAULT_TARGET_NM / df["total_conc"] * df["share"] * DEFAULT_TOTAL_VOLUME_TARGET

        return {"df": df, "enumerate": enumerate}
    
    def validate(self) -> bool:
        if not super().validate():
            return False
            
        return True
    
    def process_request(self, **context) -> Response:
        if not self.validate():
            return self.make_response(**context)
        
        experiment: models.Experiment = context["experiment"]
        user: models.User = context["user"]
        df = db.get_experiment_lanes_df(experiment.id)

        for i, pool_reads_form in enumerate(self.pool_reads_forms):
            df.loc[i, "num_m_reads_requested"] = pool_reads_form.m_reads.data

        data = []
        for i, lane_target_form in enumerate(self.lane_target_forms):
            data.append({
                "target_total_volume": lane_target_form.target_total_volume.data,
                "target_concentration": lane_target_form.target_concentration.data,
            })

        df["pipet"] = None
        df["share"] = None
        df["target_total_volume"] = None
        df["target_concentration"] = None
        df["total_conc"] = df["qubit_concentration"] / (df["avg_library_size"] * 660) * 1_000_000

        for i, pool_reads_form in enumerate(self.pool_reads_forms):
            df.at[i, "num_m_reads_requested"] = pool_reads_form.m_reads.data

        for lane, _df in df.groupby("lane"):
            target = data[lane - 1]  # type: ignore
            df.loc[_df.index, "share"] = _df["num_m_reads_requested"] / _df["num_m_reads_requested"].sum()
            df.loc[_df.index, "target_total_volume"] = target["target_total_volume"]
            df.loc[_df.index, "target_concentration"] = target["target_concentration"]

        for _, _df in df.groupby("lane"):
            df.loc[_df.index, "pipet"] = _df["target_concentration"] / _df["total_conc"] * _df["share"] * _df["target_total_volume"]

        logger.debug(df["pipet"])
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

        db_file = db.create_file(
            name=filename,
            type=FileType.LANE_POOLING_TABLE,
            extension=extension,
            uploader_id=user.id,
        )

        filepath = os.path.join(current_app.config["MEDIA_FOLDER"], db_file.path)
        db.add_file_to_experiment(experiment.id, db_file.id)

        df.to_csv(filepath, sep="\t", index=False)

        experiment.status_id = ExperimentStatus.LANED.id
        experiment = db.update_experiment(experiment)

        logger.debug(f"File '{db_file.path}' uploaded by user '{user.id}'.")
        flash("Laning Completed!", "success")

        return make_response(redirect=url_for("experiments_page.experiment_page", experiment_id=experiment.id))