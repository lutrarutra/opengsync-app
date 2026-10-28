from typing import Literal, Sequence
from pathlib import Path

import premailer
import smtplib

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from starlette.datastructures import URL

from opengsync_db import models

from .config import settings, secret_value
from . import templates, responses
from ..utils import parsing


class Mailer:
    def __init__(self):
        self.sender = settings.MAIL_SENDER
        self.sender_address = settings.MAIL_SENDER
        self.smtp_server = settings.MAIL_SERVER
        self.smtp_user = settings.MAIL_USER
        self.smtp_password = settings.MAIL_PASSWORD
        self.smtp_port = settings.MAIL_PORT
        self.use_tls = True
        self._email_style: str | None = None

    def _get_email_style(self) -> str:
        if self._email_style is None:
            path = Path(settings.app_config.static_folder) / "style" / "email.css"
            self._email_style = path.read_text()
        return self._email_style

    def send_welcome_back(self, recipient_email: str):
        style = self._get_email_style()
        self.__send_email(
            recipients=recipient_email,
            subject="Welcome back to OpeNGSync!",
            body=templates.render_template("email/welcome-back.html", support_email=settings.app_config.personalization.email, style=style),
            mime_type="html"
        )

    def send_registration(self, recipient_email: str, verification_link: str | URL):
        style = self._get_email_style()
        self.__send_email(
            recipients=recipient_email,
            subject="Welcome to OpeNGSync!",
            body=templates.render_template("email/register-user.html", link=verification_link, style=style),
            mime_type="html"
        )

    def send_activation(self, recipient_email: str, activation_link: str | URL):
        style = self._get_email_style()
        self.__send_email(
            recipients=recipient_email,
            subject="OpeNGSync Account Activation",
            body=templates.render_template("email/user-activation.html", link=activation_link, style=style),
            mime_type="html"
        )

    def send_password_reset(self, recipient_email: str, reset_link: str | URL):
        style = self._get_email_style()
        self.__send_email(
            recipients=recipient_email,
            subject="OpeNGSync Password Reset",
            body=templates.render_template("email/password-reset.html", link=reset_link, style=style),
            mime_type="html"
        )

    def send_share_paths(
        self,
        recipients: Sequence[str],
        share_token,
        author,
        browse_link: str,
    ):
        style = self._get_email_style()

        body = templates.render_template(
            "email/share-paths.html",
            style=style,
            browse_link=browse_link,
            author=author,
            share_token=share_token,
        )

        self.__send_email(
            recipients=list(set(recipients)),
            subject=f"{settings.app_config.personalization.organization} Shared Data with You",
            body=body,
            mime_type="html",
        )

    def send_share_project_data(
        self,
        recipients: Sequence[str],
        share_token: models.ShareToken,
        current_user: models.User,
        project: models.Project,
        internal_share: bool,
        anonymous: bool = False,
        comment: str | None = None,
    ):
        style = self._get_email_style()
        browse_link = str(responses.external_url_for("file_share.browse", token=share_token.uuid))

        internal_share_content = ""
        template_folder = Path(settings.app_config.template_folder)
        internal_template = settings.app_config.personalization.internal_share_template
        if internal_share and internal_template:
            if (template_folder / internal_template).exists():
                mapping = {}
                if settings.app_config.share_path_mapping is not None:
                    mapping = settings.app_config.share_path_mapping
                internal_paths = parsing.filter_subpaths([data_path.path for data_path in project.data_paths])
                internal_paths = [parsing.replace_substrings(path, mapping) for path in internal_paths]
                internal_share_content = templates.render_template(
                    internal_template, paths=internal_paths, project=project,
                )

        library_types = project.library_types

        email_header = ""
        header_path = "custom/share-project-data-email-header.html"
        if (template_folder / header_path).exists():
            email_header = templates.render_template(
                header_path, project=project,
                internal_share_content=internal_share_content,
                library_types=library_types,
            )

        email_footer = ""
        footer_path = "custom/share-project-data-email-footer.html"
        if (template_folder / footer_path).exists():
            email_footer = templates.render_template(
                footer_path, project=project, library_types=library_types,
            )

        body = templates.render_template(
            "email/share-project-data.html",
            style=style,
            browse_link=browse_link,
            project=project,
            library_types=library_types,
            author=None if anonymous else current_user if current_user.is_insider else None,
            experiments=project.experiments,
            seq_requests=project.seq_requests,
            share_token=share_token,
            email_header=email_header,
            email_footer=email_footer,
            comment=comment,
        )

        self.__send_email(
            recipients=list(set(recipients)),
            subject=f"[{project.identifier or f'P{project.id}'}]: {settings.app_config.personalization.organization} Shared Project Data",
            body=body,
            mime_type="html",
        )

    def __send_email(self, recipients: str | Sequence[str], subject: str, body: str, mime_type: Literal["plain", "html"] = "plain"):
        if mime_type == "html":
            body = premailer.transform(body)
        
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()

            server.login(self.smtp_user, secret_value(self.smtp_password))
            server.auth_plain()

            if isinstance(recipients, str):
                recipients = [recipients]
            
            message = MIMEMultipart()
            message["From"] = self.sender_address
            message["To"] = ', '.join(recipients)
            message["Subject"] = subject
            
            message.attach(MIMEText(body, mime_type))
            server.send_message(message, from_addr=self.sender_address, to_addrs=recipients)