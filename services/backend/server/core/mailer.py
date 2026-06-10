from typing import Literal, Sequence
import premailer
import smtplib
import jinja2 as j2

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from starlette.datastructures import URL

from .config import settings
from . import templates


class Mailer:
    def __init__(self):
        self.sender = settings.MAIL_SENDER
        self.sender_address = settings.MAIL_SENDER
        self.smtp_server = settings.MAIL_SERVER
        self.smtp_user = settings.MAIL_USER
        self.smtp_password = settings.MAIL_PASSWORD
        self.smtp_port = settings.MAIL_PORT
        self.use_tls = True
        self.j2_loader = j2.PackageLoader(package_name="server", package_path="/templates")
        self.j2_env = j2.Environment(loader=self.j2_loader, undefined=j2.StrictUndefined if settings.ENVIRONMENT != "prod" else j2.Undefined)

    async def send_welcome_back(self, recipient_email: str):
        style = open("/static/style/compiled/email.css").read()
        self.__send_email(
            recipients=recipient_email,
            subject="Welcome back to OpeNGSync!",
            body=self.j2_env.get_template("email/welcome-back.html").render(support_email=settings.app_config.personalization.email, style=style),
            mime_type="html"
        )

    async def send_registration(self, recipient_email: str, verification_link: str | URL):
        style = open("/static/style/compiled/email.css").read()
        self.__send_email(
            recipients=recipient_email,
            subject="Welcome to OpeNGSync!",
            body=self.j2_env.get_template("email/register-user.html").render(link=verification_link, style=style),
            mime_type="html"
        )
    
    def __send_email(self, recipients: str | Sequence[str], subject: str, body: str, mime_type: Literal["plain", "html"] = "plain"):
        if mime_type == "html":
            body = premailer.transform(body)
        
        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()

            server.login(self.smtp_user, self.smtp_password)
            server.auth_plain()

            if isinstance(recipients, str):
                recipients = [recipients]
            
            message = MIMEMultipart()
            message["From"] = self.sender_address
            message["To"] = ', '.join(recipients)
            message["Subject"] = subject
            
            message.attach(MIMEText(body, mime_type))
            server.send_message(message, from_addr=self.sender_address, to_addrs=recipients)