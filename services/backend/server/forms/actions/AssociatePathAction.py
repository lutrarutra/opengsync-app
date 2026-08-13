from pathlib import Path

from fastapi import Depends, Query

from opengsync_db import queries as Q, SyncSession, exceptions as db_exc, categories as C

from ...core import dependencies, responses, config
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class AssociatePathAction(HTMXForm):
    template_path = "workflows/share/associate-path.html"

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

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = Path(path)
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit").include_query_params(
            path=self.path.as_posix(),
        )

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            path: str = Query(..., description="Relative path under the share root."),
        ) -> "AssociatePathAction":
            return AssociatePathAction(path=path)
        return dependency

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
            share_root = Path(config.settings.app_config.share_root)
            full_path = share_root / form.path

            file_type = C.DataPathType.CUSTOM
            if full_path.is_dir():
                file_type = C.DataPathType.DIRECTORY
            else:
                ext = full_path.suffix.lower()
                if ext == ".html":
                    file_type = C.DataPathType.HTML
                elif ext == ".pdf":
                    file_type = C.DataPathType.PDF
                elif ext in [".tsv", ".csv"]:
                    file_type = C.DataPathType.TABLE
                elif ext in [".xlsx", ".xls"]:
                    file_type = C.DataPathType.EXCEL
                elif ext in [".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp"]:
                    file_type = C.DataPathType.IMAGE

            posix_path = form.path.as_posix()

            if form.project.data is not None:
                try:
                    session.save(Q.data_path.create(
                        path=posix_path,
                        type=file_type,
                        project=session.get_one(Q.project.select(id=int(form.project.data))),
                    ))
                except db_exc.LinkAlreadyExists:
                    pass

            if form.experiment.data is not None:
                try:
                    session.save(Q.data_path.create(
                        path=posix_path,
                        type=file_type,
                        experiment=session.get_one(Q.experiment.select(id=int(form.experiment.data))),
                    ))
                except db_exc.LinkAlreadyExists:
                    pass

            if form.seq_request.data is not None:
                try:
                    session.save(Q.data_path.create(
                        path=posix_path,
                        type=file_type,
                        seq_request=session.get_one(Q.seq_request.select(id=int(form.seq_request.data))),
                    ))
                except db_exc.LinkAlreadyExists:
                    pass

            if form.library.data is not None:
                try:
                    session.save(Q.data_path.create(
                        path=posix_path,
                        type=file_type,
                        library=session.get_one(Q.library.select(id=int(form.library.data))),
                    ))
                except db_exc.LinkAlreadyExists:
                    pass

            parent = form.path.parent
            kwargs = {} if parent == Path() or parent.as_posix() == "." else {"subpath": parent.as_posix()}
            return responses.htmx_response(redirect=responses.url_for("browser_page", **kwargs))
        return route
