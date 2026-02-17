import json
import smtplib
import os

from flask import Response, flash, render_template, url_for
from flask_htmx import make_response
from wtforms import StringField, BooleanField, SelectField, EmailField
from wtforms.validators import DataRequired, Optional as OptionalValidator

from opengsync_db import models
from opengsync_db.categories import LibraryType, ProjectStatus, DeliveryStatus

from .... import db, logger, mail_handler
from ....tools import utils
from ....core import exceptions, runtime
from ...HTMXFlaskForm import HTMXFlaskForm


class ShareProjectDataForm(HTMXFlaskForm):
    _template_path = "workflows/share_project_data/share-1.html"
    
    anonymous_send = BooleanField("Anonymous Send")
    internal_share = BooleanField("Internal Access Share", default=False)
    time_valid_min = SelectField("Link Validity Period: ", choices=[
        (60 * 24, "24 Hours"),
        (60 * 72, "3 Days"),
        (60 * 24 * 7, "1 Week"),
        (60 * 24 * 14, "2 Week"),
        (60 * 24 * 30, "1 Month"),
    ], default=60 * 24 * 14, coerce=int)

    send_to_owner = BooleanField("Send to Project Owner: ", default=False)
    custom_email = EmailField("Recipient: ", validators=[OptionalValidator()])
    recipients = StringField(validators=[DataRequired()])
    mark_project_delivered = BooleanField("Mark Project as Delivered", default=True)
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

        if not current_user.is_insider() and self.time_valid_min.data > self.time_valid_min.default:
            self.error_dummy.errors = (f"You don't have permissions to create that lasts more than {self.time_valid_min.default}",)
            return False
        
        if not current_user.is_insider() and self.custom_email.data:
            self.error_dummy.errors = ("You don't have permissions to send to custom email addresses.",)
            return False

        if len(self.paths) == 0:
            self.error_dummy.errors = ("No data paths available to share.",)
            return False
        
        recipients: list[str] = json.loads(self.recipients.data)  # type: ignore
        
        if self.send_to_owner.data:
            if self.project.owner.email not in recipients:
                recipients.append(self.project.owner.email)

        self.recipient_emails = list(set(recipients))

        if self.custom_email.data:
            self.recipient_emails.append(self.custom_email.data)

        if not self.recipient_emails:
            self.error_dummy.errors = ("No recipients selected.",)
            return False
        
        return True

    def process_request(self, current_user: models.User) -> Response:
        if not self.validate(current_user):
            logger.debug(self.errors)
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

        if self.mark_project_delivered.data:
            self.project.status = ProjectStatus.DELIVERED
        self.project.share_token = share_token
        db.projects.update(self.project)
        
        outdir = self.project.identifier or "output"
        http_command = render_template("snippets/rclone-http.sh.j2", token=share_token.uuid, outdir=outdir)
        sync_command = render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid, outdir=outdir)
        wget_command = render_template("snippets/wget.sh.j2", token=share_token.uuid, outdir=outdir)
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()

        browse_link = runtime.url_for("file_share.browse", token=share_token.uuid, _external=True)

        library_types = {library.type for library in self.project.libraries}
        tenx_contents = any(set(LibraryType.get_tenx_library_types()).intersection(library_types))

        seq_requests = db.seq_requests.find(project_id=self.project.id, limit=None, sort_by="id")[0]
        experiments = db.experiments.find(project_id=self.project.id, limit=None, sort_by="id")[0]

        internal_share_content = ""
        if (template := runtime.app.personalization.get("internal_share_template")):
            if os.path.exists(os.path.join(runtime.app.template_folder, template)):
                internal_paths = self.project.data_paths
                internal_paths = utils.filter_subpaths([data_path.path for data_path in internal_paths])
                internal_paths = [utils.replace_substrings(path, runtime.app.share_path_mapping) for path in internal_paths]
                internal_share_content = render_template(
                    template, paths=internal_paths, project=self.project
                )
            else:
                logger.info(f"Internal share template '{template}' not found.")

        content = render_template(
            "email/share-data.html", style=style, browse_link=browse_link,
            project=self.project, tenx_contents=tenx_contents, library_types=library_types,
            author=None if self.anonymous_send.data else current_user if current_user.is_insider() else None,
            seq_requests=seq_requests, experiments=experiments, share_token=share_token,
            internal_access_share=self.internal_share.data,
            internal_share_content=internal_share_content,
            sync_command=sync_command,
            http_command=http_command,
            wget_command=wget_command,
            outdir=outdir
        )
        if not runtime.app.debug:
            try:
                mail_handler.send_email(
                    recipients=self.recipient_emails,
                    subject=f"[{self.project.identifier or f'P{self.project.id}'}]: {runtime.app.personalization['organization']} Shared Project Data",
                    body=content, mime_type="html",
                )
            except smtplib.SMTPException as e:
                logger.error(f"Failed to send email to {self.recipient_emails}: {e}")
                raise e
        else:
            logger.info(f"Email would be sent to: {self.recipient_emails}")

        for seq_request in self.project.seq_requests:
            for link in seq_request.delivery_email_links:
                if link.email in self.recipient_emails:
                    link.status = DeliveryStatus.DISPATCHED
                    db.seq_requests.update(seq_request)

        flash("Data Share Email Sent!", "success")
        return make_response(redirect=url_for("projects_page.project", project_id=self.project.id, tab="project-data_paths-tab"))



        
        

            