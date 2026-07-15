import os
import uuid as uuid_lib
from typing import Literal

from fastapi import Depends, Response, Query

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, dependencies, exceptions as exc, config
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


class MediaFileForm(HTMXForm):
    template_path = "forms/file-upload.html"
    MAX_SIZE_MBYTES: int = 5

    file_type = inputs.selectable.SelectableInputField(
        "File Type", options=C.MediaFileType.as_selectable(), description="Select the type of file you are uploading.",
    )
    comment = inputs.string.TextAreaInputField(
        "Comment", max_length=4096, required=False, description="Provide a brief description of the file.",
    )
    file = inputs.file.FileInputField("File", max_size=MAX_SIZE_MBYTES, allowed_extensions=["tsv", "xlsx", "csv", "pdf", "png", "jpg", "jpeg"])

    def __init__(
        self,
        form_type: Literal["create", "edit"],
        file: models.MediaFile | None = None,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ) -> None:
        super().__init__()
        self.media_file = file
        self.form_type = form_type
        self.seq_request_id = seq_request_id
        self.experiment_id = experiment_id
        self.lab_prep_id = lab_prep_id
        if self.form_type == "create" and self.media_file is not None:
            raise ValueError("file must be None when form_type is 'create'")
        if self.form_type == "edit" and self.media_file is None:
            raise ValueError("file must be provided when form_type is 'edit'")
        
        url_context = {}
        if self.seq_request_id is not None:
            url_context["seq_request_id"] = self.seq_request_id
        if self.experiment_id is not None:
            url_context["experiment_id"] = self.experiment_id
        if self.lab_prep_id is not None:
            url_context["lab_prep_id"] = self.lab_prep_id
        self.post_url = responses.url_for("MediaFileForm.Upload").include_query_params(**url_context)

    @staticmethod
    def check_permissions(
        session: SyncSession,
        current_user: models.User,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ):
        if seq_request_id is not None:
            if session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to upload files to this sequencing request.")

        if experiment_id is not None or lab_prep_id is not None:
            if not current_user.is_insider:
                raise exc.NoPermissionsException("You do not have permission to upload files to this resource.")

    @classmethod
    def Init(cls, form_type: Literal["create", "edit"]) -> FormFunc:
        def dependency(
            seq_request_id: int | None = None,
            experiment_id: int | None = None,
            lab_prep_id: int | None = None,
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
        ) -> "MediaFileForm":
            MediaFileForm.check_permissions(
                session=session,
                current_user=current_user,
                seq_request_id=seq_request_id,
                experiment_id=experiment_id,
                lab_prep_id=lab_prep_id,
            )

            return MediaFileForm(
                form_type=form_type,
                seq_request_id=seq_request_id,
                experiment_id=experiment_id,
                lab_prep_id=lab_prep_id,
            )

        return dependency

    @htmx_route("GET", "/upload", name="Upload")
    def RenderUpload(cls) -> RouteFunc:
        def route(
            form: "MediaFileForm" = Depends(MediaFileForm.Init(form_type="create")),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/upload", name="Upload")
    def Upload(cls) -> RouteFunc:
        def submit(
            form: MediaFileForm = Depends(MediaFileForm.Validate(form_type="create")),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            seq_request_id: int | None = Query(None),
            experiment_id: int | None = Query(None),
            lab_prep_id: int | None = Query(None),
        ) -> Response:
            if seq_request_id is not None:
                redirect = responses.url_for("seq_request_page", seq_request_id=seq_request_id)
            elif experiment_id is not None:
                redirect = responses.url_for("experiment_page", experiment_id=experiment_id)
            elif lab_prep_id is not None:
                redirect = responses.url_for("lab_prep_page", lab_prep_id=lab_prep_id)
            else:
                raise exc.BadRequestException("At least one of seq_request_id, experiment_id, or lab_prep_id must be provided.")
            
            MediaFileForm.check_permissions(
                session=session,
                current_user=current_user,
                seq_request_id=seq_request_id,
                experiment_id=experiment_id,
                lab_prep_id=lab_prep_id,
            )

            if not form.file.data.filename:
                raise exc.BadRequestException("No file was uploaded.")

            try:
                file_type = C.MediaFileType.get(int(str(form.file_type.data)))
            except (ValueError, TypeError):
                raise exc.BadRequestException("Invalid file type.")

            filename = form.file.data.filename
            _, ext = os.path.splitext(filename)
            if file_type.extensions and ext.lower() not in file_type.extensions:
                raise exc.BadRequestException(f"File type '{file_type.label}' does not support '{ext}' files.")

            content = form.file.data.content
            if content is None:
                raise exc.BadRequestException("No file was uploaded.")
            
            size_bytes = form.file.data.size
            if size_bytes and size_bytes > MediaFileForm.MAX_SIZE_MBYTES * 1024 * 1024:
                raise exc.BadRequestException(f"File size exceeds {MediaFileForm.MAX_SIZE_MBYTES} MB limit.")

            file_uuid = str(uuid_lib.uuid4())
            file_ext = ext.lower()
            file_name = filename.rsplit(".", 1)[0][:64]

            media_dir = config.settings.app_config.media_folder
            file_dir = os.path.join(media_dir, file_type.dir)
            os.makedirs(file_dir, exist_ok=True)
            file_path = os.path.join(file_dir, f"{file_uuid}{file_ext}")

            with open(file_path, "wb") as f:
                f.write(content)

            session.save(Q.media_file.create(
                name=file_name,
                type=file_type,
                uploader_id=current_user.id,
                extension=file_ext,
                size_bytes=size_bytes,
                uuid=file_uuid,
                seq_request_id=seq_request_id,
                experiment_id=experiment_id,
                lab_prep_id=lab_prep_id,
            ))
            return responses.htmx_response(redirect=redirect, flash=responses.flash("File uploaded successfully!", "success"))
        return submit



    
