

from fastapi import Request
from fastapi.responses import Response

from opengsync_db import models, categories as C, SyncSession

from ...core import exceptions, responses
from ..HTMXForm import HTMXForm
from ...components import inputs


class FlowCellDesignForm(HTMXForm):
    template_path = "forms/flow_cell_design.html"

    name = inputs.string.StringInputField("Name", max_length=models.FlowCellDesign.name.type.length)
    flow_cell_type_id = inputs.selectable.SelectableInputField(
        "Flow Cell Type",
        options=[(-1, "-")] + C.FlowCellType.as_selectable(),
        default=-1,
        required=False,
    )

    def __init__(
        self,
        request: Request,
        flow_cell_design: models.FlowCellDesign | None = None,
    ):
        super().__init__(request)
        self.flow_cell_design = flow_cell_design
        self._context["flow_cell_design"] = flow_cell_design

    def prepare(self) -> None:
        if self.flow_cell_design is None:
            return
        self.name.data = self.flow_cell_design.name
        self.flow_cell_type_id.data = self.flow_cell_design.flow_cell_type_id or -1

    def _save(self) -> None:
        session: SyncSession = self.request.state.db_session
        if self.flow_cell_design is not None:
            self.flow_cell_design.name = self.name.data
            self.flow_cell_design.flow_cell_type_id = (
                self.flow_cell_type_id.data if self.flow_cell_type_id.data != -1 else None
            )
        else:
            new_design = models.FlowCellDesign(
                name=self.name.data,
                flow_cell_type_id=(
                    self.flow_cell_type_id.data if self.flow_cell_type_id.data != -1 else None
                ),
            )
            session.add(new_design)

    def process_request(self) -> Response:
        self.validate()
        self._save()
        return responses.htmx_response(
            redirect=responses.url_for("design"),
            flash=responses.flash("Changes Saved!", "success"),
        )