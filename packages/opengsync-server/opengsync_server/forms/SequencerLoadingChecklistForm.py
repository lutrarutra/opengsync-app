import os
import numpy as np
import datetime as dt
from flask import Response, flash, url_for, render_template_string
from flask_wtf import FlaskForm
from flask_htmx import make_response
from wtforms.validators import DataRequired
from markupsafe import Markup
from wtforms import FloatField, HiddenField, StringField, FieldList, FormField

from opengsync_db import models, categories as cats

from ..core.RunTime import runtime
from ..tools import utils
from .HTMXFlaskForm import HTMXFlaskForm
from .. import db, logger

class ParameterSubForm(FlaskForm):
    param_label = StringField("Parameter", validators=[DataRequired()])
    param_value = FloatField("Value", validators=[DataRequired()])
    var_name = HiddenField(validators=[DataRequired()])

class SequencerLoadingChecklistForm(HTMXFlaskForm):
    _template_path = "forms/sequencer_loading_checklist_form.html"

    parameters = FieldList(FormField(ParameterSubForm), label="Parameters")

    def __init__(self, current_user: models.User, experiment: models.Experiment, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.experiment = experiment
        self.current_user = current_user
        self._context["experiment"] = experiment

        if self.experiment.workflow.load_sequencer_workflow_checklist is None:
            raise ValueError("Experiment workflow does not have a sequencer loading checklist template associated with it.")
        
        if not os.path.exists(path := os.path.join(runtime.app.static_folder, "resources", "templates", "seq_loading", self.experiment.workflow.load_sequencer_workflow_checklist)):
            raise FileNotFoundError(f"Sequencer loading checklist template not found at path: {path}")
        
        with open(path, "r") as f:
            raw_md = f.read()

        self.__params, self.template_md = utils.parse_markdown_template(raw_md)

    def prepare(self):
        for param in self.__params:
            logger.debug(param)
            if param["type"] == "number":
                self.parameters.append_entry({
                    "param_label": param["label"],
                    "param_value": param.get("default", None),
                    "var_name": param["var_name"]
                })
            elif param["type"] == "list":
                for lane in self.experiment.lanes:
                    self.parameters.append_entry({
                        "param_label": f"{param['label']} (Lane {lane.number})",
                        "param_value": param.get("default", None),
                        "var_name": f"{param['var_name']}_lane_{lane.number}"
                    })
                
    def validate(self) -> bool:
        if (validated := super().validate()) is False:
            return False
        
        return validated
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        template_context = {}
        for subform in self.parameters:
            var_key = subform.var_name.data      # e.g., 'naoh'
            var_value = subform.param_value.data # e.g., 7.5
            template_context[var_key] = var_value
            
        df = db.pd.get_experiment_laned_pools(self.experiment.id)[["lane", "pool_name"]]
        df["lane"] = df["lane"].astype(str)
        df = df.groupby("lane", sort=True).agg(lambda x: ";".join(sorted(x))).reset_index()
        df = df.groupby("pool_name", sort=False).agg(lambda x: ",".join(sorted(x))).reset_index()
        df["PhiX [µL]"] = 0.0
        for idx, row in df.iterrows():
            df.at[idx, "PhiX [µL]"] += template_context.get(f"phi_x_lane_{row['lane']}", 0.0)
        df["count"] = df["lane"].apply(lambda x: len(x.split(",")))
        df["Pool [µL]"] = template_context.get("pool_volume", np.nan) * df["count"]
        df["NaOH [µL]"] = template_context.get("naoh", np.nan) * df["count"]
        df["Pre-load Buffer [µL]"] = template_context.get("preload", np.nan) * df["count"]

        lane_table = df[["lane", "pool_name", "Pool [µL]", "NaOH [µL]", "PhiX [µL]"]].rename(columns={"lane": "Lane", "pool_name": "Pool"})
        preload_table = df[["lane", "pool_name", "Pre-load Buffer [µL]"]].rename(columns={"lane": "Lane", "pool_name": "Pool"})
            
        template_context["lane_table"] = Markup(lane_table.to_html(index=False, classes="table", border=0, justify="left"))
        template_context["pre_load_buffer_table"] = Markup(preload_table.to_html(index=False, classes="table", border=0, justify="left"))
        self.template_md = (
            f"""# Experiment {self.experiment.name}\n- Generated: {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n- Workflow: {self.experiment.workflow.display_name}\n- Operator: {self.current_user.name}\n""" +
            f"""- Read Config. {self.experiment.read_config}\n""" +
            f"""{"\n".join([f"- `{subform.param_label.data}`: {subform.param_value.data}" for subform in self.parameters])}\n\n""" +
            self.template_md
        )
        final_markdown_text = render_template_string(self.template_md, **template_context)

        file = db.media_files.create(
            name="sequencer_loading_checklist",
            type=cats.MediaFileType.SEQUENCER_LOADING_CHECKLIST,
            uploader_id=self.current_user.id,
            extension=".md",
            size_bytes=len(final_markdown_text.encode("utf-8")),
            experiment_id=self.experiment.id
        )

        with open(os.path.join(runtime.app.media_folder, cats.MediaFileType.SEQUENCER_LOADING_CHECKLIST.dir, f"{file.uuid}.md"), "w") as f:
            f.write(final_markdown_text)
        
        flash("Checklist Generated!", "success")
        return make_response(redirect=url_for("experiments_page.experiment", experiment_id=self.experiment.id, tab="checklist-tab"))