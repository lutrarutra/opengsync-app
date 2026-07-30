import os

from fastapi import Depends

from opengsync_db import queries as Q, SyncSession, models

from ...core.mailer import Mailer
from ...core import dependencies, exceptions as exc, responses, config
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


TIME_VALID_CHOICES = [
    (60 * 24, "24 Hours"),
    (60 * 72, "3 Days"),
    (60 * 24 * 7, "1 Week"),
    (60 * 24 * 14, "2 Week"),
    (60 * 24 * 30, "1 Month"),
]


class ShareDirectoryAction(HTMXForm):
    template_path = "actions/share-directory.html"

    directory_path = inputs.string.StringInputField(
        "Directory Path",
        required=True,
        read_only=True,
    )
    time_valid_min = inputs.selectable.SelectableInputField(
        "Link Validity Period",
        TIME_VALID_CHOICES,
        default=TIME_VALID_CHOICES[3][0],
    )
    recipients = inputs.string.TextAreaInputField(
        "Recipients",
        required=True,
        description="Comma-separated email addresses",
    )
    anonymous_send = inputs.boolean.CheckboxInputField("Anonymous Send")

    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        self.path = path
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            path: str | None = None,
        ) -> "ShareDirectoryAction":
            return ShareDirectoryAction(path=path)
        return dependency

    @htmx_route("GET", "/share-directory")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "ShareDirectoryAction" = Depends(ShareDirectoryAction.Init()),
            _=Depends(dependencies.require_insider),
            path: str | None = None,
        ):
            if path is not None:
                form.directory_path.data = path
            return form.make_response()
        return route

    @htmx_route("POST", "/share-directory")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ShareDirectoryAction" = Depends(ShareDirectoryAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
            mailer: Mailer = Depends(dependencies.mail_client),
        ):
            if not current_user.is_insider:
                raise exc.NoPermissionsException()

            # Parse and validate recipients
            recipients = [email.strip() for email in form.recipients.data.split(",") if email.strip()]
            if not recipients:
                form.recipients.errors.append("At least one recipient email is required.")
                raise exc.FormValidationException(form)

            for email in recipients:
                if not email or "@" not in email:
                    form.recipients.errors.append(f"Invalid email address: {email}")
                    raise exc.FormValidationException(form)

            # Validate directory path exists under share_root
            share_root = config.settings.app_config.share_root
            directory_path = form.directory_path.data
            if not directory_path:
                form.directory_path.errors.append("Directory path is required.")
                raise exc.FormValidationException(form)

            p = os.path.join(share_root, directory_path)
            if not os.path.exists(p):
                form.directory_path.errors.append("Directory path does not exist on server.")
                raise exc.FormValidationException(form)

            try:
                resolved = os.path.realpath(p)
                share_root_resolved = os.path.realpath(share_root)
                relative = os.path.relpath(resolved, share_root_resolved)
                if relative.startswith(".."):
                    form.directory_path.errors.append("Directory path is outside of share root.")
                    raise exc.FormValidationException(form)
            except ValueError:
                form.directory_path.errors.append("Directory path is outside of share root.")
                raise exc.FormValidationException(form)

            if not os.path.isdir(p):
                form.directory_path.errors.append("Directory path must be a directory, not a file.")
                raise exc.FormValidationException(form)

            share_path = relative

            # Create share token
            share_token = session.save(Q.share_token.create(
                owner=current_user,
                time_valid_min=form.time_valid_min.data,
                paths=[share_path],
            ), flush=True)

            # Send email
            browse_link = str(responses.url_for("file_share.browse", token=share_token.uuid))
            mailer.send_share_directory(
                recipients=list(set(recipients)),
                share_token=share_token,
                author=None if form.anonymous_send.data else current_user,
                browse_link=browse_link,
            )

            return responses.htmx_response(
                flash=responses.flash("Email Sent!", "success"),
            )
        return route