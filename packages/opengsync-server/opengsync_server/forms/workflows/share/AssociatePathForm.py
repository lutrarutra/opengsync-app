from pathlib import Path

from flask import Response, url_for
from flask_htmx import make_response
from wtforms import FormField

from opengsync_db import models, exceptions
from opengsync_db.categories import DataPathType

from .... import db, logger
from ...HTMXFlaskForm import HTMXFlaskForm
from ...SearchBar import OptionalSearchBar


class AssociatePathForm(HTMXFlaskForm):
    selected_users: list[models.User]
    _template_path = "workflows/share/associate-path.html"

    project = FormField(OptionalSearchBar, label="Select Project")
    experiment = FormField(OptionalSearchBar, label="Select Experiment")
    seq_request = FormField(OptionalSearchBar, label="Select Seq Request")
    library = FormField(OptionalSearchBar, label="Select Library")

    def __init__(self, path: Path, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.post_url = url_for("files_htmx.associate_path", path=path.as_posix())
        self.path = path
        self._project = None
        self._experiment = None
        self._seq_request = None
        self._library = None

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if (project_id := self.project.selected.data) is not None:
            self._project = db.projects[int(project_id)]
        if (experiment_id := self.experiment.selected.data) is not None:
            self._experiment = db.experiments[int(experiment_id)]
        if (seq_request_id := self.seq_request.selected.data) is not None:
            self._seq_request = db.seq_requests[int(seq_request_id)]
        if (library_id := self.library.selected.data) is not None:
            self._library = db.libraries[int(library_id)]

        return True

    def process_request(self) -> Response:
        if not self.validate():
            logger.debug(self.errors)
            return self.make_response()
        
        file_type = DataPathType.CUSTOM
        if self.path.is_dir():
            file_type = DataPathType.DIRECTORY
        elif not self.path.is_file():
            ext = self.path.suffix.lower()
            if ext == ".html":
                file_type = DataPathType.HTML
            elif ext == ".pdf":
                file_type = DataPathType.PDF
            elif ext in [".tsv", ".csv"]:
                file_type = DataPathType.TABLE
            elif ext in [".xlsx", ".xls"]:
                file_type = DataPathType.EXCEL
            elif ext in [".png", ".jpg", ".jpeg", ".gif", ".tiff", ".bmp"]:
                file_type = DataPathType.IMAGE
        
        try:
            if self._project is not None:
                db.data_paths.create(
                    path=self.path.as_posix(),
                    type=file_type,
                    project=self._project,
                )
        except exceptions.LinkAlreadyExists as e:
            pass
        
        if self._experiment is not None:
            try:
                db.data_paths.create(
                    path=self.path.as_posix(),
                    type=file_type,
                    experiment=self._experiment,
                )
            except exceptions.LinkAlreadyExists as e:
                pass
            
        if self._seq_request is not None:
            try:
                db.data_paths.create(
                    path=self.path.as_posix(),
                    type=file_type,
                    seq_request=self._seq_request,
                )
            except exceptions.LinkAlreadyExists as e:
                pass
            
        if self._library is not None:
            try:
                db.data_paths.create(
                    path=self.path.as_posix(),
                    type=file_type,
                    library=self._library,
                )
            except exceptions.LinkAlreadyExists as e:
                pass

        return make_response(redirect=url_for("browser_page.files", subpath=self.path.parent))

            