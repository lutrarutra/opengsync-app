import resend
import premailer
import jinja2 as j2

from .config import settings


class Mailer:
    def __init__(self):
        resend.api_key = settings.RESEND_API_KEY
        self.sender = settings.EMAIL_SENDER
        self.j2_loader = j2.PackageLoader(package_name="server", package_path="templates/email")
        self.j2_env = j2.Environment(loader=self.j2_loader, undefined=j2.StrictUndefined)

    def send_registration_email(self, recipient_email: str, verification_link: str):
        html_content = premailer.transform(
            self.j2_env.get_template("register.jinja").render(link=verification_link)
        )
        self.__send_email(recipient_email, "Welcome to CodeFlower!", html_content)
    
    def __send_email(self, to: str, subject: str, html: str):
        try:
            resend.Emails.send(
                resend.Emails.SendParams({
                    "from": self.sender,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                })
            )
        except Exception as e:
            print(f"Error sending email: {e}", flush=True)