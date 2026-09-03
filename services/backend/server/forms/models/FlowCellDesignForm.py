from fastapi import Depends, Response

from opengsync_db import SyncSession, models, queries as Q, categories as C

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import FormFunc, HTMXForm, RouteFunc, htmx_route


class FlowCellDesignForm(HTMXForm):
    """Create or edit a flow-cell design."""

    template_path = "forms/flow_cell_design.html"

    name = inputs.string.StringInputField(
        "Name",
        max_length=models.FlowCellDesign.name.type.length,
        min_length=1,
    )
    flow_cell_type_id = inputs.selectable.SelectableInputField(
        "Flow Cell Type",
        options=[(-1, "-")] + C.FlowCellType.as_selectable(),
        default=-1,
    )

    def __init__(self, flow_cell_design: models.FlowCellDesign | None = None) -> None:
        super().__init__()
        self.flow_cell_design = flow_cell_design

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            flow_cell_design_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "FlowCellDesignForm":
            design = None
            if flow_cell_design_id is not None:
                design = session.get_one(Q.flow_cell_design.select(id=flow_cell_design_id))
            return cls(flow_cell_design=design)

        return dependency

    @htmx_route("GET", "/edit-flow-cell-design", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "FlowCellDesignForm" = Depends(FlowCellDesignForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            if form.flow_cell_design is None:
                raise exc.OpeNGSyncServerException("Flow cell design ID must be provided for edit form.")
            form.populate_from_design()
            return form.make_response()
        return route

    @htmx_route("POST", "/edit-flow-cell-design", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "FlowCellDesignForm" = Depends(FlowCellDesignForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.flow_cell_design is None:
                raise exc.OpeNGSyncServerException("Flow cell design ID must be provided for edit form.")
            form.edit(session)
            return responses.htmx_response(
                redirect=responses.url_for("design"),
                flash=responses.flash("Changes Saved!", "success"),
            )
        return submit

    def populate_from_design(self) -> None:
        if self.flow_cell_design is None:
            return
        self.name.data = self.flow_cell_design.name
        self.flow_cell_type_id.data = self.flow_cell_design.flow_cell_type_id or -1

    def _set_design_values(self) -> None:
        if self.flow_cell_design is None:
            raise exc.OpeNGSyncServerException("Flow cell design must be provided for edit.")
        self.flow_cell_design.name = self.name.data
        self.flow_cell_design.flow_cell_type_id = (
            None if self.flow_cell_type_id.data == -1 else self.flow_cell_type_id.data
        )

    def edit(self, session: SyncSession) -> models.FlowCellDesign:
        self._set_design_values()
        assert self.flow_cell_design is not None
        return session.save(self.flow_cell_design, flush=True)
