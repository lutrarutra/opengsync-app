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
    mux_type = inputs.selectable.SelectableInputField("Multiplexing Type", required=False, options=C.MUXType.as_selectable())
    nuclei_isolation = inputs.boolean.CheckboxInputField("Nuclei Isolation")

    def __init__(self, library: models.Library) -> None:
        super().__init__()
        self.library = library
        self.post_url = responses.url_for("LibraryForm.Edit", library_id=library.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            library_id: int,
            session: SyncSession = Depends(dependencies.db_session)
        ) -> "LibraryForm":
            library = session.get_one(Q.library.select(id=library_id))
            return LibraryForm(library=library)

        return dependency

    @htmx_route("GET", "/{library_id}/edit", name="Edit")
    def RenderEdit(cls) -> RouteFunc:
        def route(
            form: "LibraryForm" = Depends(LibraryForm.Init())
        ):
            form.name.data = form.library.sample_name
            form.library_type.data = form.library.type_id
            form.genome.data = form.library.genome_ref_id
            form.status.data = form.library.status_id
            form.mux_type.data = form.library.mux_type_id
            form.nuclei_isolation.data = form.library.nuclei_isolation
            return form.make_response()
        return route

    @htmx_route("POST", "/{library_id}/edit", name="Edit")
    def Edit(cls) -> RouteFunc:
        def submit(
            session: SyncSession = Depends(dependencies.db_session),
            form: "LibraryForm" = Depends(LibraryForm.Validate()),
        ) -> Response:
            # Validate name characters
            if error := _check_name(form.name.data):
                form.name.errors.append(error)
                raise exc.FormValidationException(form)

            form.library.sample_name = form.name.data
            form.library.name = f"{form.library.sample_name}_{form.library.type.identifier}"
            form.library.type = C.LibraryType.get(form.library_type.data)
            form.library.genome_ref = C.GenomeRef.get(form.genome.data)
            form.library.status = C.LibraryStatus.get(form.status.data)
            form.library.mux_type = C.MUXType.get(form.mux_type.data) if form.mux_type.data else None
            form.library.nuclei_isolation = form.nuclei_isolation.data
            session.save(form.library)

            return responses.htmx_response(
                redirect=responses.url_for("library_page", library_id=form.library.id),
                flash=responses.flash(f"Updated library '{form.library.name}'.", "success"),
            )
        return submit