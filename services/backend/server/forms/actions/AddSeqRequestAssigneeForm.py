from fastapi import Request

from opengsync_db import models

from ...components import inputs
from ..HTMXForm import HTMXForm


class AddSeqRequestAssigneeForm(HTMXForm):
    template_path = "forms/add-seq_request-assignee.html"

    user_id = inputs.searchable.SearchableInputField(
        "Select User", route="search_users", required=True
    )

    def __init__(
        self,
        request: Request,
        seq_request: models.SeqRequest,
        current_user: models.User,
    ):
        super().__init__(request)
        self.seq_request = seq_request
        self.current_user = current_user

    async def prepare(self) -> None:
        if self.current_user not in self.seq_request.assignees:
            self.user_id.data = str(self.current_user.id)
