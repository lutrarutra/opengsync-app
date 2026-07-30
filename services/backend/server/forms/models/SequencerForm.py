from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class SequencerForm(HTMXForm):
    template_path = "forms/sequencer.html"

    name = inputs.string.StringInputField(
        "Sequencer Name",
        max_length=models.Sequencer.name.type.length,
        required=True,
    )
    model = inputs.selectable.SelectableInputField(
        "Sequencer Model",
        C.SequencerModel.as_selectable(),
        required=True,
    )
    ip_address = inputs.string.StringInputField(
        "IP Address",
        max_length=models.Sequencer.ip.type.length,
        required=False,
    )

    def __init__(self, sequencer: models.Sequencer | None = None) -> None:
        super().__init__()
        self.sequencer = sequencer
        if sequencer is not None:
            self.post_url = responses.url_for("SequencerForm.Edit", sequencer_id=sequencer.id)
        else:
            self.post_url = responses.url_for("SequencerForm.Create")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            sequencer_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
        ) -> "SequencerForm":
            sequencer = None
            if sequencer_id is not None:
                sequencer = session.get_one(Q.sequencer.select(id=sequencer_id))
            return SequencerForm(sequencer=sequencer)

        return dependency

    @htmx_route("GET", "/{sequencer_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "SequencerForm" = Depends(SequencerForm.Init()),
        ):
            if form.sequencer is None:
                raise exc.OpeNGSyncServerException("Sequencer ID must be provided for edit form.")

            form.name.data = form.sequencer.name
            form.model.data = form.sequencer.model_id
            form.ip_address.data = form.sequencer.ip
            return form.make_response()
        return route

    @htmx_route("GET", "/create", name="Create")
    def RenderCreate(cls) -> RouteFunc:
        def route(
            form: "SequencerForm" = Depends(SequencerForm.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/{sequencer_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "SequencerForm" = Depends(SequencerForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if form.sequencer is None:
                raise exc.OpeNGSyncServerException("Sequencer ID must be provided for edit form.")

            if session.exists(Q.sequencer.select(name=form.name.data).where(models.Sequencer.id != form.sequencer.id)):
                form.name.errors.append("You already have a sequencer with this name.")
                raise exc.FormValidationException(form)

            form.sequencer.name = form.name.data
            form.sequencer.ip = form.ip_address.data
            form.sequencer.model = C.SequencerModel.get(form.model.data)

            return responses.htmx_response(
                redirect=responses.url_for("sequencer_page", sequencer_id=form.sequencer.id),
                flash=responses.flash("Sequencer updated.", "success"),
            )
        return submit

    @htmx_route("POST", "/create", name="Create")
    def Create(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "SequencerForm" = Depends(SequencerForm.Validate()),
            _=Depends(dependencies.require_insider),
        ) -> Response:
            if session.exists(Q.sequencer.select(name=form.name.data)):
                form.name.errors.append("You already have a sequencer with this name.")
                raise exc.FormValidationException(form)

            sequencer = session.save(Q.sequencer.create(
                name=form.name.data,
                model=C.SequencerModel.get(form.model.data),
                ip=form.ip_address.data,
            ), flush=True)

            return responses.htmx_response(
                redirect=responses.url_for("devices_page"),
                flash=responses.flash(f"Sequencer '{sequencer.name}' created.", "success"),
            )
        return submit