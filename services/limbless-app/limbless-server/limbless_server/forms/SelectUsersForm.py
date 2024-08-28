from typing import Optional

import pandas as pd
import json

from flask import url_for
from wtforms import StringField

from limbless_db import models, DBSession
from limbless_db.categories import SampleStatusEnum, LibraryStatusEnum, PoolStatusEnum, SampleStatus, LibraryStatus, PoolStatus

from .. import db, logger
from .HTMXFlaskForm import HTMXFlaskForm


class SelectUsersForm(HTMXFlaskForm):
    _template_path = "forms/select-users.html"
    _form_label = "select_users_form"

    selected_user_ids = StringField()

    def __init__(self, formdata: Optional[dict[str, str]] = None):
        super().__init__(formdata=formdata)

    def validate(self) -> bool:
        if not super().validate():
            return False
        
        if (selected_users_ids := self.selected_user_ids.data) is None:
            return False
        
        if len(selected_users_ids := json.loads(selected_users_ids)) == 0:
            return False
        
        self.user_ids = []
        try:
            for user_id in selected_users_ids:
                self.user_ids.append(int(user_id))
        except ValueError:
            self.selected_user_ids.errors = ("Invalid user ID",)
            return False
        
        self._context["selected_users"] = self.user_ids
        return True