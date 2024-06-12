from typing import Optional

import json

from flask import Response, url_for, flash
from flask_htmx import make_response
from wtforms import StringField

from limbless_db import DBSession, models

from .... import logger, db
from ...HTMXFlaskForm import HTMXFlaskForm


class SelectLibrariesForm(HTMXFlaskForm):
    _template_path = "workflows/library_pooling/pooling-2.html"
    _form_label = "library_pooling_form"

    selected_library_ids = StringField()
    removed_library_ids = StringField()

    def __init__(self, pool: models.Pool, formdata: dict = {}, uuid: Optional[str] = None):
        if uuid is None:
            uuid = formdata.get("file_uuid")
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.pool = pool
        self._context["pool"] = pool

    def prepare(self):
        libraries, _ = db.get_libraries(pool_id=self.pool.id, limit=None)
        self._context["libraries"] = libraries
        self._context["current_libraries"] = [library.id for library in libraries]

    def validate(self) -> bool:
        validated = super().validate()

        if (selected_library_ids := self.selected_library_ids.data) is None:
            selected_library_ids = []
        else:
            selected_library_ids = json.loads(selected_library_ids)
        
        self.add_library_ids = []
        try:
            for library_id in selected_library_ids:
                library_id = int(library_id)
                self.add_library_ids.append(library_id)
                if (library := db.get_library(library_id)) is None:
                    self.selected_library_ids.errors = [f"Library {library_id} not found"]
                    return False
                if library.pool_id is not None:
                    self.selected_library_ids.errors = [f"Library {library_id} is already pooled"]
                    return False
        except ValueError:
            self.selected_library_ids.errors = ["Invalid library id"]
            return False
        
        self.remove_library_ids = []
        if (removed_library_ids := self.removed_library_ids.data) is not None:
            removed_library_ids = json.loads(removed_library_ids)
            try:
                for library_id in removed_library_ids:
                    library_id = int(library_id)
                    self.remove_library_ids.append(library_id)
                    if (library := db.get_library(library_id)) is None:
                        self.removed_library_ids.errors = [f"Library {library_id} not found"]
                        return False
                    if library.pool_id != self.pool.id:
                        self.removed_library_ids.errors = [f"Library {library_id} is not in the pool"]
                        return False
            except ValueError:
                self.removed_library_ids.errors = ["Invalid library id"]
                return False

        self._context["selected_libraries"] = self.add_library_ids
        self._context["removed_libraries"] = self.remove_library_ids
        return validated

    def process_request(self) -> Response:
        if not self.validate():
            return self.make_response()
        
        with DBSession(db) as session:
            for library_id in self.add_library_ids:
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")
                
                session.link_library_pool(library.id, self.pool.id)

            for library_id in self.remove_library_ids:
                if (library := session.get_library(library_id)) is None:
                    logger.error(f"Library {library_id} not found")
                    raise ValueError(f"Library {library_id} not found")
                library.pool_id = None
                library = session.update_library(library)

        flash("Changes saved to pool", "success")
        return make_response(redirect=url_for("pools_page.pool_page", pool_id=self.pool.id))