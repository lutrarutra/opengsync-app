from typing import Sequence, Literal

import premailer
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


from .. import logger


class MailHandler:
    sender_address: str
    smtp_server: str
    smtp_user: str
    smtp_password: str
    smtp_port: int
    use_tls: bool
    __initialized = False

    def init_app(self, sender_address: str, smtp_server: str, smtp_user: str, smtp_password: str, smtp_port: int = 587, use_tls: bool = True):
        self.sender_address = sender_address
        self.smtp_server = smtp_server
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        self.__initialized = True

    def send_email(self, recipients: str | Sequence[str], subject: str, body: str, mime_type: Literal["plain", "html"] = "plain"):
        if not self.__initialized:
            raise RuntimeError("MailHandler not initialized. Call init_app() before using this method.")
        
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


        
        
