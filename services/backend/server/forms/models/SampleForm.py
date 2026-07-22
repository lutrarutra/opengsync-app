from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


def _check_sample_name(val: str) -> str | None:
    """Validate sample name: only letters, digits, underscores, and dots allowed."""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")
    for c in val:
        if c not in allowed:
            return f"Invalid character in name: '{c}'. You can only use letters, digits and the following special characters: ['_', '.']"
    return None


class SampleForm(HTMXForm):
    template_path = "forms/sample.html"

    name = inputs.string.StringInputField(
        "Sample Name", max_length=models.Sample.name.type.length, min_length=3,
    )
    status = inputs.selectable.SelectableInputField(
        "Status", required=False, options=C.SampleStatus.as_selectable(),
    )

    def __init__(self, sample: models.Sample) -> None:
        super().__init__()
        self.sample = sample
        self.post_url = responses.url_for("SampleForm.Edit", sample_id=sample.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            sample_id: int,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "SampleForm":
            sample = session.get_one(Q.sample.select(id=sample_id))
            return SampleForm(sample=sample)

        return dependency

    @htmx_route("GET", "/{sample_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "SampleForm" = Depends(SampleForm.Init())
        ):
            form.name.data = form.sample.name
            form.status.data = form.sample.status_id
            return form.make_response()
        return route

    @htmx_route("POST", "/{sample_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "SampleForm" = Depends(SampleForm.Validate()),
    ) -> Response:
            # Validate name characters
            if error := _check_sample_name(form.name.data):
                form.name.errors.append(error)
                raise exc.FormValidationException(form)

            for user_sample in form.sample.project.samples:
                if form.name.data == user_sample.name and form.sample.id != user_sample.id:
                    form.name.errors.append("Project already has a sample with this name.")
                    raise exc.FormValidationException(form)

            form.sample.name = form.name.data
            form.sample.status_id = form.status.data
            session.save(form.sample)

            return responses.htmx_response(
                redirect=responses.url_for("sample_page", sample_id=form.sample.id),
                flash=responses.flash("Changes saved!", "success"),
            )
        return submit