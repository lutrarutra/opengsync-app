

from flask import Response, flash, url_for
from flask_htmx import make_response
from wtforms import FormField

from opengsync_db import models

from .. import logger, db
from .HTMXFlaskForm import HTMXFlaskForm
from .SearchBar import SearchBar


class AddSeqRequestAssigneeForm(HTMXFlaskForm):
    _template_path = "forms/add-seq_request-assignee.html"

    user = FormField(SearchBar, label="Select User")

    def __init__(self, seq_request: models.SeqRequest, current_user: models.User, formdata: dict | None = None):
        super().__init__(formdata=formdata)
        self.seq_request = seq_request
        self.current_user = current_user
        self._context["seq_request"] = seq_request

    def prepare(self) -> None:
        if self.current_user not in self.seq_request.assignees:
            self.user.selected.data = self.current_user.id
            self.user.search_bar.data = self.current_user.name

    def validate(self):
        if not super().validate():
            return False

        if self.user.selected.data is None:
            self.user.selected.errors = ("Please select a user.",)
            return False

        assignee = db.users[self.user.selected.data]

        if not assignee.is_insider():
            self.user.selected.errors = ("Only insider users can be assigned to requests.",)
            return False
        
        if assignee in self.seq_request.assignees:
            self.user.selected.errors = (f"User {assignee.name} is already an assignee in this request.",)
            return False
        
        return True
    
    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        assignee = db.users[self.user.selected.data]
        self.seq_request.assignees.append(assignee)
        db.seq_requests.update(self.seq_request)
        
        flash(f"Assignee Added Successfully!", "success")
        return make_response(redirect=url_for("seq_requests_page.seq_request", seq_request_id=self.seq_request.id, tab="request-assignees-tab"))