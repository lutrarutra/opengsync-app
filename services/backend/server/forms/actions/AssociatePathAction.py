from pathlib import Path

from fastapi import Depends, Query
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession

from ...core import dependencies, responses, config, exceptions as exc
from ...utils.file_browser import is_within_root, is_share_root, infer_data_path_type
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..common import SelectedPathsMixin, SelectedPathSubForm


def _associations(data_paths: list[models.DataPath]) -> list[dict[str, str | None]]:
    """Same badges, in the same order, as components/file-browser/entries.html renders."""
    associations: list[dict[str, str | None]] = []
    for data_path in data_paths:
        if data_path.project:
            associations.append({
                "label": data_path.project.identifier or data_path.project.title,
                "href": str(responses.url_for("project_page", project_id=data_path.project.id)),
            })
        if data_path.experiment:
            associations.append({"label": data_path.experiment.name, "href": None})
        if data_path.seq_request:
            associations.append({"label": data_path.seq_request.name, "href": None})
        if data_path.library:
            associations.append({
                "label": data_path.library.name,
                "href": str(responses.url_for("library_page", library_id=data_path.library.id)),
            })
    return associations


class AssociatePathAction(HTMXForm, SelectedPathsMixin):
    """Links one or more share-root paths to a project/experiment/request/library."""
    template_path = "workflows/share/associate-path.html"

    paths = inputs.dynamic.SubFormList[SelectedPathSubForm](min_elements=1)
    project = inputs.searchable.SearchableInputField(
        "Select Project", route="search_projects", required=False,
    )
    experiment = inputs.searchable.SearchableInputField(
        "Select Experiment", route="search_experiments", required=False,
    )
    seq_request = inputs.searchable.SearchableInputField(
        "Select Seq Request", route="search_seq_requests", required=False,
    )
    library = inputs.searchable.SearchableInputField(
        "Select Library", route="search_libraries", required=False,
    )

    def __init__(self, initial_paths: list[str] | None = None) -> None:
        super().__init__()
        self.initial_paths = initial_paths or []
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            path: list[str] = Query(default=[], description="Relative paths under the share root, to prefill."),
        ) -> "AssociatePathAction":
            return AssociatePathAction(initial_paths=path)
        return dependency

    def prepare(self) -> None:
        self.prefill_paths(self.initial_paths)

    @htmx_route("GET", "/associate-path")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "AssociatePathAction" = Depends(AssociatePathAction.Init()),
            _=Depends(dependencies.require_insider),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/associate-path")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "AssociatePathAction" = Depends(AssociatePathAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            _=Depends(dependencies.require_insider),
        ):
            form.assert_path_count()

            # Every path is checked before anything is saved, so one bad path rejects them all
            share_root = Path(config.settings.app_config.share_root)
            for entry in form.paths:
                if not is_within_root(share_root, entry.path.data):
                    entry.path.errors.append("Path is outside of share root.")
                elif is_share_root(entry.path.data):
                    entry.path.errors.append("A whole share folder can't be associated, only files and folders inside it.")
            if form.paths.has_errors:
                raise exc.FormValidationException(form)

            # A folder already covers the paths inside it
            paths = [Path(path) for path in form.collapse_paths(entry.path.data for entry in form.paths)]

            # (field, query module, DataPath keyword); an existing association is skipped, as legacy
            # intended (its LinkAlreadyExists handling never fired, so it stored duplicates)
            targets = []
            for field, query, key in (
                (form.project, Q.project, "project"),
                (form.experiment, Q.experiment, "experiment"),
                (form.seq_request, Q.seq_request, "seq_request"),
                (form.library, Q.library, "library"),
            ):
                if field.data is not None:
                    targets.append((session.get_one(query.select(id=int(field.data))), key))

            updated: list[dict] = []
            for path in paths:
                posix_path = path.as_posix()
                file_type = infer_data_path_type(share_root / path)
                for target, key in targets:
                    if session.first(Q.data_path.select(path=posix_path, **{f"{key}_id": target.id})) is not None:
                        continue
                    session.save(Q.data_path.create(path=posix_path, type=file_type, **{key: target}))

                session.flush()
                data_paths = session.get_all(
                    statement=Q.data_path.select(path=posix_path),
                    limit=None,
                    options=[
                        orm.joinedload(models.DataPath.project),
                        orm.joinedload(models.DataPath.experiment),
                        orm.joinedload(models.DataPath.seq_request),
                        orm.joinedload(models.DataPath.library),
                    ],
                )
                updated.append({"path": posix_path, "associations": _associations(data_paths)})

            return responses.htmx_response(
                flash=responses.flash(f"{len(paths)} paths associated." if len(paths) > 1 else "Path associated.", "success"),
                trigger={"dataPathAssociationsUpdated": {"paths": updated}},
            )
        return route
