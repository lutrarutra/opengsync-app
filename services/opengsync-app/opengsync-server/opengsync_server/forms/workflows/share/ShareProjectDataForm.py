import json
import smtplib
import os

from flask import Response, url_for, flash, render_template
from flask_htmx import make_response
from wtforms import StringField, BooleanField, SelectField
from wtforms.validators import DataRequired

from opengsync_db import models
from opengsync_db.categories import AccessType, LibraryType

from .... import db, logger, mail_handler
from ....tools import utils
from ....core import exceptions, runtime
from ...HTMXFlaskForm import HTMXFlaskForm


class ShareProjectDataForm(HTMXFlaskForm):
    selected_users: list[models.User]
    _template_path = "workflows/share_project_data/share-1.html"

    anonymous_send = BooleanField("Anonymous Send")
    internal_share = BooleanField("Internal Access Share", default=False)
    time_valid_min = SelectField("Link Validity Period: ", choices=[
        (60 * 1, "1 Hour"),
        (60 * 3, "3 Hours"),
        (60 * 6, "6 Hours"),
        (60 * 12, "12 Hours"),
        (60 * 24, "24 Hours"),
        (60 * 38, "2 Days"),
        (60 * 72, "3 Days"),
        (60 * 24 * 7, "1 Week"),
    ], default=60 * 24 * 3, coerce=int)

    send_to_owner = BooleanField("Send to Project Owner: ", default=True)
    selected_user_ids = StringField(validators=[DataRequired()])
    error_dummy = StringField()

    def __init__(self, project: models.Project, formdata: dict | None = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.project = project
        self._context["project"] = project
        self.post_url = url_for("share_project_data_workflow.share_project_data", project_id=project.id)
        self.paths = utils.filter_subpaths([data_path.path for data_path in self.project.data_paths])
        self.data_paths = [data_path for data_path in self.project.data_paths if data_path.path in self.paths]

    def validate(self, current_user: models.User) -> bool:
        if not super().validate():
            return False
        
        selected_user_ids = self.selected_user_ids.data

        if not current_user.is_insider() and self.time_valid_min.data > self.time_valid_min.default:
            self.error_dummy.errors = (f"You don't have permissions to create that lasts more than {self.time_valid_min.default}",)
            return False

        if len(self.paths) == 0:
            self.error_dummy.errors = ("No data paths available to share.",)
            return False

        if not selected_user_ids:
            self.error_dummy.errors = ("No users selected.",)
            return False
        
        selected_user_ids = json.loads(selected_user_ids)
        if not isinstance(selected_user_ids, list) or not all(isinstance(i, int) for i in selected_user_ids):
            logger.error(f"Invalid selected_user_ids data: {selected_user_ids}")
            raise exceptions.InternalServerErrorException("Invalid data received.")
        
        if self.send_to_owner.data:
            if self.project.owner_id not in selected_user_ids:
                selected_user_ids.append(self.project.owner_id)
        
        self.selected_users = []
        for user_id in set(selected_user_ids):
            if (user := db.users.get(user_id)) is None:
                logger.error(f"User with id {user_id} not found.")
                raise exceptions.InternalServerErrorException(f"User with id {user_id} not found.")
            
            access_type = db.projects.get_access_type(self.project, user)
            if access_type < AccessType.VIEW:
                self.error_dummy.errors = (f"User '{user.id}' does not have access to the project.",)
                return False
            self.selected_users.append(user)

        if not self.selected_users:
            self.error_dummy.errors = ("No valid users selected.",)
            return False
        
        return True

    def process_request(self, current_user: models.User) -> Response:
        if not self.validate(current_user):
            return self.make_response()
        
        if (share_token := self.project.share_token) is not None:
            if not share_token._expired:
                share_token._expired = True
                db.shares.update(share_token)
        
        share_token = db.shares.create(
            owner=current_user,
            time_valid_min=self.time_valid_min.data,
            paths=self.paths,
        )

        self.project.share_token = share_token
        db.projects.update(self.project)
        
        http_command = render_template("snippets/rclone-http.sh.j2", token=share_token.uuid)
        sync_command = render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid)
        wget_command = render_template("snippets/wget.sh.j2", token=share_token.uuid)
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

        browse_link = url_for("file_share.browse", token=share_token.uuid, _external=True)

        library_types = {library.type for library in self.project.libraries}
        tenx_contents = any(set(LibraryType.get_tenx_library_types()).intersection(library_types))

        seq_requests = db.seq_requests.find(project_id=self.project.id, limit=None, sort_by="id")[0]
        experiments = db.experiments.find(project_id=self.project.id, limit=None, sort_by="id")[0]

        content = render_template(
            "email/share-data.html", style=style, browse_link=browse_link,
            project=self.project, tenx_contents=tenx_contents, library_types=library_types,
            author=None if self.anonymous_send.data else current_user if current_user.is_insider() else None,
            seq_requests=seq_requests, experiments=experiments, share_token=share_token,
            share_path_mapping=runtime.app.share_path_mapping,
            internal_access_share=self.internal_share.data,
            sync_command=sync_command,
            http_command=http_command,
            wget_command=wget_command,
        )

        recipients = [user.email for user in self.selected_users]
        
        try:
            mail_handler.send_email(
                recipients=recipients,
                subject=f"[{self.project.identifier or f'P{self.project.id}'}]: BSF Shared Project Data",
                body=content, mime_type="html",
            )
        except smtplib.SMTPException as e:
            logger.error(f"Failed to send email to {recipients}: {e}")
            raise e

        flash("Data Share Email Sent!", "success")
        return make_response(redirect=url_for("projects_page.project", project_id=self.project.id, tab="project-data_paths-tab"))



        
        

            