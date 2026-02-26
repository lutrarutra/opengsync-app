import smtplib
import os

from flask import Response, flash, render_template, request
from flask_htmx import make_response
from wtforms import StringField, BooleanField, SelectField
from wtforms.validators import DataRequired

from opengsync_db import models

from .. import db, logger, mail_handler
from ..tools import utils
from ..core import runtime
from .HTMXFlaskForm import HTMXFlaskForm


class DirectoryShareForm(HTMXFlaskForm):
    _template_path = "workflows/share/share-directory.html"
    
    directory_path = StringField("Directory Path", validators=[DataRequired()])
    anonymous_send = BooleanField("Anonymous Send", default=False)
    time_valid_min = SelectField("Link Validity Period: ", choices=[
        (60 * 24, "24 Hours"),
        (60 * 72, "3 Days"),
        (60 * 24 * 7, "1 Week"),
        (60 * 24 * 14, "2 Week"),
        (60 * 24 * 30, "1 Month"),
    ], default=60 * 24 * 14, coerce=int)

    recipients = StringField("Recipients", validators=[DataRequired()])

    def __init__(self, path: str | None = None, formdata: dict | None = None):
        self.path = path
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.post_url = runtime.url_for("files_htmx.share_directory")

    def prepare(self):
        if self.path is not None:
            self.directory_path.data = self.path

    def validate(self, current_user: models.User) -> bool:
        if not super().validate():
            return False
        
        if not current_user.is_insider():
            return False
        
        if not self.recipients.data:
            self.recipients.errors = ("At least one recipient email is required.",)
            return False
        
        recipients: list[str] = [email.strip() for email in self.recipients.data.split(",") if email.strip()]
        for email in recipients:
            if not utils.is_valid_email(email):
                self.recipients.errors = (f"Invalid email address: {email}",)
                return False
            
        self._recipients = list(set(recipients))

        if not self.directory_path.data:
            self.directory_path.errors = ("Directory path is required.",)
            return False
        
        if not (p := runtime.app.share_root / self.directory_path.data).exists():
            self.directory_path.errors = ("Directory path does not exist on server.",)
            return False
        
        try:
            p = p.resolve(strict=True).relative_to(runtime.app.share_root.resolve())
        except ValueError:
            self.directory_path.errors = ("Directory path is outside of share root.",)
            return False
        
        if p.is_file():
            self.directory_path.errors = ("Directory path must be a directory, not a file.",)
            return False
        self.p = p
        return True
    
    def process_request(self, current_user: models.User) -> Response:
        if not self.validate(current_user):
            return self.make_response()
        
        share_token = db.shares.create(
            owner=current_user,
            time_valid_min=self.time_valid_min.data,
            paths=[self.p.as_posix()],
        )

        outdir = self.p.name

        http_command = render_template("snippets/rclone-http.sh.j2", token=share_token.uuid, outdir=outdir)
        sync_command = render_template("snippets/rclone-sync.sh.j2", token=share_token.uuid, outdir=outdir)
        wget_command = render_template("snippets/wget.sh.j2", token=share_token.uuid, outdir=outdir)
        style = open(os.path.join(runtime.app.static_folder, "style/compiled/email.css")).read()
        browse_link = runtime.url_for("file_share.browse", token=share_token.uuid, _external=True)

        content = render_template(
            "email/share-directory.html", style=style, browse_link=browse_link,
            author=None if self.anonymous_send.data else current_user if current_user.is_insider() else None,
            share_token=share_token,
            sync_command=sync_command,
            http_command=http_command,
            wget_command=wget_command,
            outdir=outdir
        )
        try:
            mail_handler.send_email(
                recipients=self._recipients,
                subject=f"{runtime.app.personalization['organization']} Shared a Directory",
                body=content, mime_type="html",
            )
        except smtplib.SMTPException as e:
            logger.error(f"Failed to send email to {self._recipients}: {e}")
            raise e
        
        flash("Email Sent!", "success")
        return make_response(redirect=request.referrer)

