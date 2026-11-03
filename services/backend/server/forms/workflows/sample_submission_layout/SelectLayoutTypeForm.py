from fastapi import Depends, Response

from opengsync_db import queries as Q, categories as C, SyncSession

from ....components import inputs
from ...HTMXForm import RouteFunc, htmx_route
from .SampleSubmissionLayoutWorkflow import SampleSubmissionLayoutWorkflow, SampleSubmissionLayoutWorkflowStep, default_kind

KIND_PLURALS = {"sample": "samples", "library": "libraries", "pool": "pools"}


class SelectLayoutTypeForm(SampleSubmissionLayoutWorkflowStep):
    template_path = "workflows/sample_submission_layout/select_type.html"

    # QC-only requests hand in samples or libraries
    KIND_OPTIONS = [
        ("sample", "Samples", "bi-droplet", "Raw samples, e.g. tissue, cells or extracted DNA/RNA."),
        ("library", "Libraries", "bi-stack", "Prepared libraries, one per tube or well."),
    ]
    LAYOUT_OPTIONS = [(t.id, t.label, t.icon, t.description) for t in C.SubmissionLayoutType]

    layout_type = inputs.selectable.SelectableInputField("Container Type", options=C.SubmissionLayoutType.as_selectable())
    kind = inputs.selectable.SelectableInputField("Items", options=[(key, label) for key, label, _, _ in KIND_OPTIONS], required=False)

    def __init__(self, workflow: SampleSubmissionLayoutWorkflow, session: SyncSession) -> None:
        super().__init__(workflow)
        self.session = session
        self.seq_request = session.get_one(Q.seq_request.select(id=workflow.seq_request_id))
        self.is_qc_only = self.seq_request.submission_type == C.SubmissionType.QC_ONLY
        self.items_label = "samples or libraries" if self.is_qc_only else KIND_PLURALS[default_kind(self.seq_request.submission_type)]

        # Pre-select what was chosen before in this run, else the saved layout
        layout_type_id = workflow.metadata.get("layout_type_id")
        kind = workflow.metadata.get("kind")
        if layout_type_id is None and self.seq_request.submission_layout_type is not None:
            layout_type_id = self.seq_request.submission_layout_type.id
        if kind is None and self.seq_request.submission_layout:
            kind = self.seq_request.submission_layout[0].kind
        self.layout_type.default = layout_type_id
        self.kind.default = kind if kind in ("sample", "library") else "sample"

    @htmx_route("GET")
    def Previous(cls) -> RouteFunc:
        def route(
            form: "SelectLayoutTypeForm" = Depends(SelectLayoutTypeForm.Init()),
        ) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SelectLayoutTypeForm" = Depends(SelectLayoutTypeForm.Validate()),
        ) -> Response:
            if form.is_qc_only:
                if form.kind.data not in ("sample", "library"):
                    form.kind.errors.append("Select what you are handing in.")
                    form.assert_valid()
                kind = form.kind.data
            else:
                kind = default_kind(form.seq_request.submission_type)

            form.workflow.header["seq_request_id"] = form.workflow.seq_request_id
            form.workflow.metadata["layout_type_id"] = form.layout_type.data
            form.workflow.metadata["kind"] = kind
            form.workflow.tables["layout_table"] = form.workflow.build_layout_table(form.session)
            return form.workflow.get_next_step(form).make_response()
        return route
