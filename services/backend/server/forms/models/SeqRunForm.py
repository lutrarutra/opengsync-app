from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class SeqRunForm(HTMXForm):
    template_path = "forms/seq_run.html"

    experiment_name = inputs.string.StringInputField(
        "Experiment Name",
        max_length=models.SeqRun.experiment_name.type.length,
        required=True,
    )
    status = inputs.selectable.SelectableInputField(
        "Status",
        C.RunStatus.as_selectable(),
        required=True,
    )
    instrument_name = inputs.string.StringInputField(
        "Instrument Name",
        max_length=models.SeqRun.instrument_name.type.length,
        required=True,
    )
    run_folder = inputs.string.StringInputField(
        "Run Folder",
        max_length=models.SeqRun.run_folder.type.length,
        required=True,
    )
    flowcell_id = inputs.string.StringInputField(
        "Flowcell ID",
        max_length=models.SeqRun.flowcell_id.type.length,
        required=True,
    )
    read_type = inputs.selectable.SelectableInputField(
        "Read Type",
        C.ReadType.as_selectable(),
        required=True,
    )
    rta_version = inputs.string.StringInputField(
        "RTA Version",
        max_length=models.SeqRun.rta_version.type.length,
        required=False,
    )
    recipe_version = inputs.string.StringInputField(
        "Recipe Version",
        max_length=models.SeqRun.recipe_version.type.length,
        required=False,
    )
    side = inputs.string.StringInputField(
        "Side",
        max_length=models.SeqRun.side.type.length,
        required=False,
    )
    flowcell_mode = inputs.string.StringInputField(
        "Flowcell Mode",
        max_length=models.SeqRun.flowcell_mode.type.length,
        required=False,
    )
    r1_cycles = inputs.numeric.IntInputField("R1 Cycles", required=False, ge=0)
    r2_cycles = inputs.numeric.IntInputField("R2 Cycles", required=False, ge=0)
    i1_cycles = inputs.numeric.IntInputField("I1 Cycles", required=False, ge=0)
    i2_cycles = inputs.numeric.IntInputField("I2 Cycles", required=False, ge=0)

    def __init__(self, seq_run: models.SeqRun | None = None) -> None:
        super().__init__()
        self.seq_run = seq_run
        if seq_run is not None:
            self.post_url = responses.url_for("SeqRunForm.Edit", seq_run_id=seq_run.id)
        else:
            self.post_url = responses.url_for("SeqRunForm.Create")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            seq_run_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SeqRunForm":
            seq_run = None
            if seq_run_id is not None:
                seq_run = session.get_one(Q.seq_run.select(id=seq_run_id))
            return SeqRunForm(seq_run=seq_run)

        return dependency

    @htmx_route("GET", "/{seq_run_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "SeqRunForm" = Depends(SeqRunForm.Init()),
        ):
            if form.seq_run is None:
                raise exc.OpeNGSyncServerException("Seq run ID must be provided for edit form.")

            form.experiment_name.data = form.seq_run.experiment_name
            form.status.data = form.seq_run.status_id
            form.instrument_name.data = form.seq_run.instrument_name
            form.run_folder.data = form.seq_run.run_folder
            form.flowcell_id.data = form.seq_run.flowcell_id
            form.read_type.data = form.seq_run.read_type_id
            form.rta_version.data = form.seq_run.rta_version
            form.recipe_version.data = form.seq_run.recipe_version
            form.side.data = form.seq_run.side
            form.flowcell_mode.data = form.seq_run.flowcell_mode
            form.r1_cycles.data = form.seq_run.r1_cycles
            form.r2_cycles.data = form.seq_run.r2_cycles
            form.i1_cycles.data = form.seq_run.i1_cycles
            form.i2_cycles.data = form.seq_run.i2_cycles
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "SeqRunForm" = Depends(SeqRunForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{seq_run_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "SeqRunForm" = Depends(SeqRunForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.seq_run is None:
                raise exc.OpeNGSyncServerException("Seq run ID must be provided for edit form.")

            if session.exists(
                Q.seq_run.select(experiment_name=form.experiment_name.data).where(
                    models.SeqRun.id != form.seq_run.id
                )
            ):
                form.experiment_name.errors.append("Experiment name not unique.")
                raise exc.FormValidationException(form)

            form.seq_run.status = C.RunStatus.get(form.status.data)
            form.seq_run.run_folder = form.run_folder.data
            form.seq_run.flowcell_id = form.flowcell_id.data
            form.seq_run.read_type = C.ReadType.get(form.read_type.data)
            form.seq_run.rta_version = form.rta_version.data
            form.seq_run.recipe_version = form.recipe_version.data
            form.seq_run.instrument_name = form.instrument_name.data
            form.seq_run.side = form.side.data
            form.seq_run.flowcell_mode = form.flowcell_mode.data
            form.seq_run.r1_cycles = form.r1_cycles.data
            form.seq_run.r2_cycles = form.r2_cycles.data
            form.seq_run.i1_cycles = form.i1_cycles.data
            form.seq_run.i2_cycles = form.i2_cycles.data

            return responses.htmx_response(
                redirect=responses.url_for("seq_run_page", seq_run_id=form.seq_run.id),
                flash=responses.flash(f"SeqRun {form.seq_run.id} edited successfully.", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "SeqRunForm" = Depends(SeqRunForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if session.exists(Q.seq_run.select(experiment_name=form.experiment_name.data)):
                form.experiment_name.errors.append("Experiment name not unique.")
                raise exc.FormValidationException(form)

            seq_run = session.save(Q.seq_run.create(
                experiment_name=form.experiment_name.data,
                status=C.RunStatus.get(form.status.data),
                instrument_name=form.instrument_name.data,
                run_folder=form.run_folder.data,
                flowcell_id=form.flowcell_id.data,
                read_type=C.ReadType.get(form.read_type.data),
                rta_version=form.rta_version.data,
                recipe_version=form.recipe_version.data,
                side=form.side.data,
                flowcell_mode=form.flowcell_mode.data,
                r1_cycles=form.r1_cycles.data,
                r2_cycles=form.r2_cycles.data,
                i1_cycles=form.i1_cycles.data,
                i2_cycles=form.i2_cycles.data,
            ), flush=True)

            if (experiment := session.first(Q.experiment.select(name=seq_run.experiment_name))) is not None:
                if seq_run.status == C.RunStatus.FINISHED:
                    experiment.status = C.ExperimentStatus.SEQUENCED
                elif seq_run.status == C.RunStatus.FAILED:
                    experiment.status = C.ExperimentStatus.FAILED
                elif seq_run.status == C.RunStatus.RUNNING:
                    experiment.status = C.ExperimentStatus.SEQUENCING
                elif seq_run.status == C.RunStatus.ARCHIVED:
                    experiment.status = C.ExperimentStatus.ARCHIVED

            return responses.htmx_response(
                redirect=responses.url_for("seq_run_page", seq_run_id=seq_run.id),
                flash=responses.flash(f"SeqRun {seq_run.id} created successfully.", "success"),
            )
        return submit