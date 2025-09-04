from typing import Sequence, Literal
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

<<<<<<< HEAD
=======
from .. import logger

>>>>>>> 3bf9919ded1998d0ff25beefa9bcbc3530e447a5

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

<<<<<<< HEAD
    def send_email(self, recipients: str | Sequence[str], subject: str, body: str, mime_type: Literal["plain", "html"] = "plain"):
        if not self.__initialized:
            raise RuntimeError("MailHandler not initialized. Call init_app() before using this method.")
        
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

=======
    def send_email(self, recipients: str | Sequence[str], subject: str, body: str, mime_type: Literal["plain", "html"] = "plain") -> bool:
        if not self.__initialized:
            raise RuntimeError("MailHandler not initialized. Call init_app() before using this method.")
        
        try:
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
        except smtplib.SMTPException as e:
            logger.error(f"Failed to send email to {recipients}: {e}")
            return False
        
        return True
>>>>>>> 3bf9919ded1998d0ff25beefa9bcbc3530e447a5

        
        
