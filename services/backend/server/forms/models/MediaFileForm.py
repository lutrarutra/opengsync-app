from typing import Literal

from fastapi import Request, UploadFile, Query, Response, Depends

from opengsync_db import queries as Q, AsyncSession, models, categories as C

from ...core import responses, exceptions as exc, config, dependencies
from ...components import inputs
from ..HTMXForm import HTMXForm



class MediaFileForm(HTMXForm):
    template_path = "forms/file-upload.html"

    file_type = inputs.selectable.SelectableInputField(
        "File Type",
        options=C.MediaFileType.as_selectable(),
        description="Select the type of file you are uploading.",
    )
    comment = inputs.string.TextAreaInputField(
        "Comment",
        max_length=4096,
        required=False,
        description="Provide a brief description of the file.",
    )

    MAX_SIZE_MBYTES: int = 5

    def __init__(
        self,
        request: Request,
        form_type: Literal["create", "edit"],
        file: models.MediaFile | None = None,
    ) -> None:
        super().__init__(request)
        self.file = file
        self.form_type = form_type
        if self.form_type == "create" and self.file is not None:
            raise ValueError("file must be None when form_type is 'create'")
        if self.form_type == "edit" and self.file is None:
            raise ValueError("file must be provided when form_type is 'edit'")

    @staticmethod
    async def check_permissions(
        session: AsyncSession,
        current_user: models.User,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ):
        if seq_request_id is not None:
            if await session.get_access_level(Q.seq_request.permissions(seq_request_id=seq_request_id, user_id=current_user.id)) < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to upload files to this sequencing request.")
        
        if experiment_id is not None or lab_prep_id is not None:
            if not current_user.is_insider():
                raise exc.NoPermissionsException("You do not have permission to upload files to this resource.")

    @staticmethod
    async def upload_file(
        request: Request,
        seq_request_id: int | None = Query(None),
        experiment_id: int | None = Query(None),
        lab_prep_id: int | None = Query(None),
        current_user: models.User = Depends(dependencies.require_user),
        session: AsyncSession = Depends(dependencies.db_session),
    ) -> Response:
        
        await MediaFileForm.check_permissions(
            session=session,
            current_user=current_user,
            seq_request_id=seq_request_id,
            experiment_id=experiment_id,
            lab_prep_id=lab_prep_id,
        )
        form = MediaFileForm(request, form_type="create")
        await form.validate()

        return await responses.htmx_response()



    
