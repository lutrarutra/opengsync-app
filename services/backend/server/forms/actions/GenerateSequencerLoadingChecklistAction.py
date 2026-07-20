import os
import datetime as dt

import numpy as np
import pandas as pd
import jinja2
from fastapi import Depends
from markupsafe import Markup

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ...core import dependencies, exceptions as exc, responses, config
from ...components import inputs
from ...utils.io import parse_markdown_template
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..SubHTMXForm import SubHTMXForm


class ParameterSubForm(SubHTMXForm):
    param_label = inputs.string.StringInputField("Parameter", required=True, read_only=True)
    param_value = inputs.numeric.FloatInputField("Value", required=True)
    var_name = inputs.string.StringInputField("var_name", hidden=True)


class GenerateSequencerLoadingChecklistAction(HTMXForm):
    template_path = "forms/sequencer_loading_checklist_form.html"

    parameters = inputs.dynamic.SubFormList[ParameterSubForm](min_elements=1)

    def __init__(self, experiment: models.Experiment, current_user: models.User) -> None:
        super().__init__()
        self.experiment = experiment
        self.current_user = current_user
        self._context["experiment"] = experiment
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", experiment_id=experiment.id)

        if self.experiment.workflow.load_sequencer_workflow_checklist is None:
            raise exc.OpeNGSyncServerException(
                "Experiment workflow does not have a sequencer loading checklist template associated with it."
            )

        template_path = os.path.join(
            config.settings.app_config.static_folder,
            "resources", "templates", "seq_loading",
            self.experiment.workflow.load_sequencer_workflow_checklist,
        )
        if not os.path.exists(template_path):
            raise exc.OpeNGSyncServerException(
                f"Sequencer loading checklist template not found at path: {template_path}"
            )

        with open(template_path, "r") as f:
            raw_md = f.read()

        self._params, self.template_md = parse_markdown_template(raw_md)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            experiment_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> "GenerateSequencerLoadingChecklistAction":
            experiment = session.get_one(Q.experiment.select(id=experiment_id))
            return cls(experiment=experiment, current_user=current_user)
        return dependency

    @htmx_route("GET", "/{experiment_id}/sequencer-loading-checklist")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "GenerateSequencerLoadingChecklistAction" = Depends(
                GenerateSequencerLoadingChecklistAction.Init()
            ),
        ):
            for param in form._params:
                if param["type"] == "number":
                    entry = form.parameters.append_entry()
                    entry.param_label._data = param["label"]
                    entry.param_value._data = param.get("default", None)
                    entry.var_name._data = param["var_name"]
                elif param["type"] == "list":
                    for lane in form.experiment.lanes:
                        entry = form.parameters.append_entry()
                        entry.param_label.data = f"{param['label']} (Lane {lane.number})"
                        entry.param_value._data = param.get("default", None)
                        entry.var_name.data = f"{param['var_name']}_lane_{lane.number}"

            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/sequencer-loading-checklist")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "GenerateSequencerLoadingChecklistAction" = Depends(
                GenerateSequencerLoadingChecklistAction.Validate()
            ),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            template_context = {}
            for subform in form.parameters:
                var_key = subform.var_name.data
                var_value = subform.param_value.data
                template_context[var_key] = var_value

            df = session.pd.get_experiment_laned_pools(form.experiment.id)[["lane", "pool_name"]]
            df["lane"] = df["lane"].astype(str)
            df = df.groupby("lane", sort=True).agg(lambda x: ";".join(sorted(x))).reset_index()
            df = df.groupby("pool_name", sort=False).agg(lambda x: ",".join(sorted(x))).reset_index()
            df["PhiX [µL]"] = 0.0
            for idx, row in df.iterrows():
                for lane in row["lane"].split(","):
                    df.at[idx, "PhiX [µL]"] += template_context.get(f"phi_x_lane_{lane}", 0.0)

            df["count"] = df["lane"].apply(lambda x: len(x.split(",")))
            df["Pool [µL]"] = template_context.get("pool_volume", np.nan) * df["count"]
            df["NaOH [µL]"] = template_context.get("naoh", np.nan) * df["count"]
            df["Pre-load Buffer [µL]"] = template_context.get("preload", np.nan) * df["count"]
            df["PhiX [µL]"] = df["PhiX [µL]"]

            lane_table = df[["lane", "pool_name", "Pool [µL]", "NaOH [µL]", "PhiX [µL]"]].rename(
                columns={"lane": "Lane", "pool_name": "Pool"}
            ).replace({0.0: ""})
            preload_table = df[["lane", "pool_name", "Pre-load Buffer [µL]"]].rename(
                columns={"lane": "Lane", "pool_name": "Pool"}
            ).replace({0.0: ""})

            template_context["lane_table"] = Markup(
                lane_table.to_html(index=False, classes="table", border=0, justify="left")
            )
            template_context["pre_load_buffer_table"] = Markup(
                preload_table.to_html(index=False, classes="table", border=0, justify="left")
            )

            form.template_md = (
                f"# Experiment {form.experiment.name}\n"
                f"- Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"- Workflow: {form.experiment.workflow.display_name}\n"
                f"- Operator: {form.current_user.name}\n"
                f"- Read Config. {form.experiment.read_config}\n"
                + "\n".join(
                    [f"- `{subform.param_label.data}`: {subform.param_value.data}" for subform in form.parameters]
                )
                + "\n\n"
                + form.template_md
            )

            final_markdown_text = jinja2.Template(form.template_md).render(**template_context)

            file = session.save(
                Q.media_file.create(
                    name="sequencer_loading_checklist",
                    type=C.MediaFileType.SEQUENCER_LOADING_CHECKLIST,
                    uploader_id=form.current_user.id,
                    extension=".md",
                    size_bytes=len(final_markdown_text.encode("utf-8")),
                    experiment_id=form.experiment.id,
                ),
                flush=True,
            )

            file_dir = os.path.join(
                config.settings.app_config.media_folder,
                C.MediaFileType.SEQUENCER_LOADING_CHECKLIST.dir,
            )
            os.makedirs(file_dir, exist_ok=True)
            file_path = os.path.join(file_dir, f"{file.uuid}.md")
            with open(file_path, "w") as f:
                f.write(final_markdown_text)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id).include_query_params(
                    tab="checklist-tab"
                ),
                flash=responses.flash("Checklist Generated!", "success"),
            )
        return route