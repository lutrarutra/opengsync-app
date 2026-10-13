from fastapi import Depends, Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


def _check_name(val: str) -> str | None:
    """Validate library name: only letters, digits, hyphens, underscores, and dots allowed."""
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    for c in val:
        if c not in allowed:
            return f"Invalid character in name: '{c}'. You can only use letters, digits and the following special characters: ['-', '_', '.']"
    return None


class LibraryForm(HTMXForm):
    template_path = "forms/library.html"

    name = inputs.string.StringInputField("Name", max_length=models.Library.sample_name.type.length, min_length=3)
    library_type = inputs.selectable.SelectableInputField("Library Type", options=C.LibraryType.as_selectable())
    genome = inputs.selectable.SelectableInputField("Reference Genome", options=C.GenomeRef.as_selectable())
    status = inputs.selectable.SelectableInputField("Status", options=C.LibraryStatus.as_selectable())
    mux_type = inputs.selectable.SelectableInputField(
        "Multiplexing Type", required=False, options=[(-1, "None")] + C.MUXType.as_selectable(),
    )
    protocol = inputs.selectable.SelectableInputField("Protocol", required=False, options=[(-1, "None")])
    nuclei_isolation = inputs.boolean.CheckboxInputField("Nuclei Isolation")

    def __init__(self, library: models.Library) -> None:
        super().__init__()
        self.library = library
        self.access_level = C.AccessLevel.NONE
        self.post_url = responses.url_for("LibraryForm.Edit", library_id=library.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            library_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.library_permissions),
        ) -> "LibraryForm":
            library = session.get_one(Q.library.select(id=library_id))
            form = LibraryForm(library=library)
            form.access_level = access_level
            form.status.read_only = access_level < C.AccessLevel.INSIDER
            form.protocol.read_only = access_level < C.AccessLevel.INSIDER
            protocols = session.get_all(Q.protocol.select(), order_by=models.Protocol.name.asc(), limit=None)
            form.protocol.set_options([(-1, "None")] + [(protocol.id, protocol.name) for protocol in protocols])
            return form

        return dependency

    @htmx_route("GET", "/{library_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            access_level: C.AccessLevel = Depends(dependencies.library_permissions),
            form: "LibraryForm" = Depends(LibraryForm.Init())
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this library.")

            form.name.data = form.library.sample_name
            form.library_type.data = form.library.type.id
            form.genome.data = form.library.genome_ref.id
            form.status.data = form.library.status.id
            form.mux_type.data = form.library.mux_type.id if form.library.mux_type is not None else -1
            form.protocol.data = form.library.protocol_id if form.library.protocol_id is not None else -1
            form.nuclei_isolation.data = form.library.nuclei_isolation
            return form.make_response()
        return route

    @htmx_route("POST", "/{library_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            access_level: C.AccessLevel = Depends(dependencies.library_permissions),
            session: SyncSession = Depends(dependencies.db_session),
            form: "LibraryForm" = Depends(LibraryForm.Validate()),
        ) -> Response:
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to edit this library.")

            # Validate name characters
            if error := _check_name(form.name.data):
                form.name.errors.append(error)
                raise exc.FormValidationException(form)

            if access_level < C.AccessLevel.INSIDER and form.status.data != form.library.status.id:
                form.status.errors.append("Only insiders can change library status.")
                raise exc.FormValidationException(form)

            protocol_id = form.protocol.data if form.protocol.data is not None and form.protocol.data != -1 else None
            if access_level < C.AccessLevel.INSIDER and protocol_id != form.library.protocol_id:
                form.protocol.errors.append("Only insiders can change library protocol.")
                raise exc.FormValidationException(form)

            if protocol_id is not None and session.first(Q.protocol.select(id=protocol_id)) is None:
                form.protocol.errors.append("Selected protocol does not exist.")
                raise exc.FormValidationException(form)

            form.library.sample_name = form.name.data
            form.library.type = C.LibraryType.get(form.library_type.data)
            form.library.name = f"{form.library.sample_name}_{form.library.type.identifier}"
            form.library.genome_ref = C.GenomeRef.get(form.genome.data)
            form.library.status = C.LibraryStatus.get(form.status.data)
            form.library.mux_type = (
                C.MUXType.get(form.mux_type.data)
                if form.mux_type.data is not None and form.mux_type.data != -1
                else None
            )
            form.library.protocol_id = protocol_id
            form.library.nuclei_isolation = form.nuclei_isolation.data
            session.save(form.library)

            return responses.htmx_response(
                redirect=responses.url_for("library_page", library_id=form.library.id),
                flash=responses.flash(f"Updated library '{form.library.name}'.", "success"),
            )
        return submit