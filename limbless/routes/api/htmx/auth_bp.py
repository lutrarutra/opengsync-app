from flask import Blueprint, url_for, render_template, flash
from flask_restful import Api, Resource
from flask_htmx import make_response
from flask_mail import Message
from flask_login import login_user, current_user, logout_user

from .... import db, forms, logger, models, bcrypt, mail, EMAIL_SENDER

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/auth/")
api = Api(auth_bp)

class Login(Resource):
    def post(self):
        login_form = forms.LoginForm()

        if not login_form.validate_on_submit():
            template = render_template(
                "forms/login.html",
                login_form=login_form
            )
            return make_response(
                template, push_url=False
            )
        
        user = db.db_handler.get_user_by_email(login_form.email.data)
        # invalid email
        if not user:
            print(login_form.errors)
            login_form.email.errors.append("Invalid email or password.")
            login_form.password.errors.append("Invalid email or password.")
            template = render_template(
                "forms/login.html",
                login_form=login_form
            )
            return make_response(
                template, push_url=False
            )

        # invalid password
        if not bcrypt.check_password_hash(user.password, login_form.password.data):
            login_form.email.errors.append("Invalid email or password.")
            login_form.password.errors.append("Invalid email or password.")
            template = render_template(
                "forms/login.html",
                login_form=login_form
            )
            return make_response(
                template, push_url=False
            )
    
        login_user(user)
        flash("Logged in.", "success")
        return make_response(
            redirect=url_for("index_page"),
        )
    
class Logout(Resource):
    def get(self):
        if current_user.is_authenticated:
            logout_user()
            flash("Logged out!", "info")

        return make_response(
            redirect=url_for("index_page"),
        )
    
class Register(Resource):
    def post(self):
        register_form = forms.RegisterForm()

        if not register_form.validate_on_submit():
            template = render_template(
                "forms/register.html",
                register_form=register_form
            )
            return make_response(
                template, push_url=False
            )

        email = register_form.email.data
        token = models.User.generate_registration_token(
            email=email
        )
        msg = Message(
            "Limbless Registration",
            sender=EMAIL_SENDER,
            recipients=[email],
            body=f"""Click the following link to register:\n
            {url_for("auth_page.register_page", token=token, _external=True)}
            """
        )
        mail.send(msg)

        flash("Email sent. Check your email for registration link.", "info")
        logger.debug(f"Registration email sent to {register_form.email.data}")
        return make_response(
            redirect=url_for("index_page"),
        )
    
class CompleteRegistration(Resource):
    def post(self, token):
        register_form = forms.CompleteRegistrationForm()

        email = models.User.verify_registration_token(
            token=token
        )
        if email is None:
            flash("Token expired or invalid.", "warning")
            return make_response(
                redirect=url_for("auth_page.auth_page"),
            )
        
        register_form.email.data = email
        
        if not register_form.validate_on_submit():
            logger.debug(register_form.errors)
            template = render_template(
                "forms/complete_register.html",
                register_form=register_form
            )
            return make_response(
                template, push_url=False
            )
        
        user = db.db_handler.create_user(
            email=register_form.email.data,
            password=register_form.password.data,
            role=models.UserRole.CLIENT
        )

        flash("Registration completed!", "success")
        logger.debug(f"Registration completed for {user.email}")
        return make_response(
            redirect=url_for("auth_page.auth_page"),
        )
    
api.add_resource(Login, "/login")
api.add_resource(Register, "/register")
api.add_resource(CompleteRegistration, "/complete_registration/<token>")
api.add_resource(Logout, "/logout")