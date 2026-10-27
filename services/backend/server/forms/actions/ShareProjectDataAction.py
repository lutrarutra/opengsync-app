import json
import smtplib

from fastapi import Depends
from loguru import logger
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C, actions
from opengsync_db.transitions import run_operation, release as release_ops

from ...core import dependencies, config, responses, exceptions as exc, redis as rds
from ...core.mailer import Mailer
from ...utils import parsing, share_fs_cache
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route


TIME_VALID_CHOICES = [
    (60 * 24, "24 Hours"),
    (60 * 72, "3 Days"),
    (60 * 24 * 7, "1 Week"),
    (60 * 24 * 14, "2 Week"),
    (60 * 24 * 30, "1 Month"),
]
DEFAULT_TIME_VALID_MIN = TIME_VALID_CHOICES[3][0]


class ShareProjectDataAction(HTMXForm):
    template_path = "workflows/share/share-project-data.html"

    anonymous_send = inputs.boolean.SwitchInputField("Anonymous Send")
    internal_share = inputs.boolean.SwitchInputField("Internal Access Share", default=False)
    time_valid_min = inputs.selectable.SelectableInputField(
        "Link Validity Period",
        TIME_VALID_CHOICES,
        default=DEFAULT_TIME_VALID_MIN,
    )
    send_to_owner = inputs.boolean.SwitchInputField("Send to Project Owner", default=False)
    custom_email = inputs.string.EmailInputField("Recipient", required=False)
    recipients = inputs.string.StringInputField("Recipients", required=False, hidden=True)
    mark_project_delivered = inputs.boolean.SwitchInputField("Mark Project as Delivered", default=True)
    comment = inputs.string.TextAreaInputField(
        "Comment", description="Optional, included in the share email.", max_length=4096, required=False,
    )

    def __init__(self, project: models.Project) -> None:
        super().__init__()
        self.project = project
        self.paths = parsing.filter_subpaths([data_path.path for data_path in project.data_paths])
        self.data_paths = [data_path for data_path in project.data_paths if data_path.path in self.paths]
        self.recipient_emails: list[str] = []
        self._context["project"] = project
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit", project_id=project.id)

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            project_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            # Sets current_user for the template, also when a CSRF failure re-renders before the route's dependencies
            _: models.User = Depends(dependencies.require_user),
        ):
            project = session.get_one(
                Q.project.select(id=project_id),
                options=[
                    orm.selectinload(models.Project.owner),
                    orm.selectinload(models.Project.data_paths),
                    orm.selectinload(models.Project.share_token),
                ],
            )
            return ShareProjectDataAction(project=project)
        return form

    def _collect_recipients(self) -> None:
        # As legacy's SelectField: only the offered validity periods
        if self.time_valid_min.data not in dict(TIME_VALID_CHOICES):
            self.time_valid_min.errors.append("Not a valid choice.")
            return

        if len(self.paths) == 0:
            self.add_general_error("No data paths available to share.")
            return

        recipients: list[str] = []
        if self.recipients.data:
            try:
                parsed = json.loads(self.recipients.data)
            except json.JSONDecodeError:
                self.add_general_error("Invalid recipients payload.")
                return
            if not isinstance(parsed, list):
                self.add_general_error("Invalid recipients payload.")
                return
            recipients = [str(email) for email in parsed if email]

        if self.send_to_owner.data and self.project.owner.email not in recipients:
            recipients.append(self.project.owner.email)

        recipient_emails = list(set(recipients))
        if self.custom_email.data:
            recipient_emails.append(self.custom_email.data)

        if not recipient_emails:
            self.add_general_error("No recipients selected.")
            return

        self.recipient_emails = recipient_emails

    # Admins and bioinformaticians only: sharing releases the data (libraries SEQUENCED → SHARED, project DELIVERED), as the release API
    @htmx_route("GET", "/{project_id}/share-data")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "ShareProjectDataAction" = Depends(ShareProjectDataAction.Init()),
            _: models.User = Depends(dependencies.require_data_assigner),
            access_level: C.AccessLevel = Depends(dependencies.project_permissions),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()
            return form.make_response()
        return route

    @htmx_route("POST", "/{project_id}/share-data")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "ShareProjectDataAction" = Depends(ShareProjectDataAction.Validate()),
            current_user: models.User = Depends(dependencies.require_data_assigner),
            access_level: C.AccessLevel = Depends(dependencies.project_permissions),
            session: SyncSession = Depends(dependencies.db_session),
            mailer: Mailer = Depends(dependencies.mail_client),
            redis: rds.RedisClient = Depends(dependencies.redis),
        ):
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException()

            form._collect_recipients()
            form.assert_valid()

            project = form.project

            if (share_token := project.share_token) is not None:
                if not share_token._expired:
                    share_token._expired = True
                    session.save(share_token)
                    share_fs_cache.invalidate(redis, share_token.uuid)

            # current_user may be a detached cache instance while project.owner (same row) is already loaded
            share_token = session.save(Q.share_token.create(
                owner=session.merge(current_user, load=False),
                time_valid_min=form.time_valid_min.data,
                paths=form.paths,
            ), flush=True)

            project.share_token = share_token
            session.save(project)

            if config.settings.ENVIRONMENT == "prod":
                try:
                    mailer.send_share_project_data(
                        recipients=form.recipient_emails,
                        share_token=share_token,
                        current_user=current_user,
                        project=project,
                        internal_share=form.internal_share.data,
                        anonymous=form.anonymous_send.data,
                        comment=form.comment.data or None,
                    )
                except smtplib.SMTPException as e:
                    logger.error(f"Failed to send email to {form.recipient_emails}: {e}")
                    raise
            else:
                logger.info(f"Email would be sent to: {form.recipient_emails}")

            # Same statuses as the release API: ticked = deliver now, unticked = deliver once all libraries are sequenced
            with run_operation(session, release_ops.SHARE_DATA, subject=project):
                actions.release_project_data(
                    session, project=project, seq_requests=project.seq_requests, recipients=form.recipient_emails,
                    mark_project_delivered=True if form.mark_project_delivered.data else None,
                )

            return responses.htmx_response(
                redirect=responses.url_for("project_page", project_id=project.id).include_query_params(
                    tab="project-data_paths-tab",
                ),
                flash=responses.flash("Data Share Email Sent!", "success"),
            )
        return route
