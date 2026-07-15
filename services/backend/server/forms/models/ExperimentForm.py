from typing import Literal

from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class ExperimentForm(HTMXForm):
    template_path = "forms/experiment.html"

    name = inputs.string.StringInputField("Experiment Name", max_length=models.Experiment.name.type.length, placeholder="e.g., EXP_2024_001")
    workflow = inputs.selectable.SelectableInputField("Workflow", options=C.ExperimentWorkFlow.as_selectable(),)
    sequencer = inputs.searchable.SearchableInputField("Sequencer", route="search_sequencers",)
    operator = inputs.searchable.SearchableInputField("Operator", route="search_users")
    status = inputs.selectable.SelectableInputField("Status", options=C.ExperimentStatus.as_selectable(), default=C.ExperimentStatus.DRAFT.id)
    r1_cycles = inputs.numeric.IntInputField("R1 Cycles", required=False)
    r2_cycles = inputs.numeric.IntInputField("R2 Cycles", required=False)
    i1_cycles = inputs.numeric.IntInputField("I1 Cycles", required=False)
    i2_cycles = inputs.numeric.IntInputField("I2 Cycles", required=False)

    def __init__(self, form_type: Literal["create", "edit"], experiment: models.Experiment | None) -> None:
        super().__init__()
        self.form_type = form_type
        self.experiment = experiment
        if experiment is None and form_type == "edit":
            raise ValueError("Experiment must be provided for edit form.")
        elif experiment is not None and form_type == "create":
            raise ValueError("Experiment must not be provided for create form.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            experiment_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "ExperimentForm":
            if form_type == "edit" and experiment_id is None:
                raise exc.OpeNGSyncServerException("Experiment ID must be provided for edit form.")
            
            experiment = None
            if experiment_id is not None:
                experiment = session.get_one(Q.experiment.select(id=experiment_id))
            return ExperimentForm(form_type=form_type, experiment=experiment)
        
        return dependency

    @htmx_route("GET", "/{experiment_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "ExperimentForm" = Depends(ExperimentForm.Init(form_type="edit")),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            if form.experiment is None:
                raise exc.OpeNGSyncServerException("Experiment ID must be provided for edit form.")
            
            form.name.data = form.experiment.name
            form.workflow.data = form.experiment.workflow_id
            form.sequencer.data = form.experiment.sequencer_id
            form.operator.data = form.experiment.operator_id
            form.status.data = form.experiment.status_id
            form.r1_cycles.data = form.experiment.r1_cycles
            form.r2_cycles.data = form.experiment.r2_cycles
            form.i1_cycles.data = form.experiment.i1_cycles
            form.i2_cycles.data = form.experiment.i2_cycles
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "ExperimentForm" = Depends(ExperimentForm.Init(form_type="create")),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            form.operator.data = current_user.id
            return form.make_response()
        return route

    @htmx_route("POST", "/{experiment_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "ExperimentForm" = Depends(ExperimentForm.Validate(form_type="edit")),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> Response:
            if form.experiment is None:
                raise exc.OpeNGSyncServerException("Experiment ID must be provided for edit form.")

            if session.exists(
                Q.experiment.select(name=form.name.data).where(models.Experiment.id != form.experiment.id)
            ):
                form.name.errors.append("An experiment with this name already exists.")
                raise exc.FormValidationException(form)

            try:
                workflow = C.ExperimentWorkFlow.get(form.workflow.data)
                status = C.ExperimentStatus.get(form.status.data)
            except ValueError as e:
                form.workflow.errors.append(str(e))
                raise exc.FormValidationException(form)

            form.experiment.name = form.name.data
            form.experiment.workflow_id = form.workflow.data
            form.experiment.sequencer_id = form.sequencer.data
            form.experiment.operator_id = form.operator.data
            form.experiment.status_id = form.status.data
            form.experiment.r1_cycles = form.r1_cycles.data
            form.experiment.r2_cycles = form.r2_cycles.data
            form.experiment.i1_cycles = form.i1_cycles.data
            form.experiment.i2_cycles = form.i2_cycles.data

            session.save(form.experiment)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=form.experiment.id),
                flash=responses.flash("Experiment Updated!", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "ExperimentForm" = Depends(ExperimentForm.Validate(form_type="create")),
            current_user: models.User = Depends(dependencies.require_insider),
        ) -> Response:
            if session.exists(Q.experiment.select(name=form.name.data)):
                form.name.errors.append("An experiment with this name already exists.")
                raise exc.FormValidationException(form)

            try:
                workflow = C.ExperimentWorkFlow.get(form.workflow.data)
                status = C.ExperimentStatus.get(form.status.data)
            except ValueError as e:
                form.workflow.errors.append(str(e))
                raise exc.FormValidationException(form)

            experiment = session.save(Q.experiment.create(
                name=form.name.data,
                workflow=workflow,
                sequencer_id=form.sequencer.data,
                operator_id=form.operator.data,
                status=status,
                r1_cycles=form.r1_cycles.data,
                r2_cycles=form.r2_cycles.data,
                i1_cycles=form.i1_cycles.data,
                i2_cycles=form.i2_cycles.data,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("experiment_page", experiment_id=experiment.id),
                flash=responses.flash("Experiment Created!", "success"),
            )
        return submit
