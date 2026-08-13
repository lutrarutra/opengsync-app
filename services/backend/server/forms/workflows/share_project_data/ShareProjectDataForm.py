from typing import Self
import json
import smtplib

from fastapi import Depends, Response
from loguru import logger
from sqlalchemy import orm

from opengsync_db import models, queries as Q, SyncSession, categories as C

from ....core import dependencies, config
from ....core.context import ctx
from ....core.mailer import Mailer
from ....utils import parsing
from ....components import inputs
from ...HTMXForm import RouteFunc, FormFunc, htmx_route
from .ShareProjectDataWorkflow import ShareProjectDataWorkflow, ShareProjectDataWorkflowStep


TIME_VALID_CHOICES = [
    (60 * 24, "24 Hours"),
    (60 * 72, "3 Days"),
    (60 * 24 * 7, "1 Week"),
    (60 * 24 * 14, "2 Week"),
    (60 * 24 * 30, "1 Month"),
]
DEFAULT_TIME_VALID_MIN = TIME_VALID_CHOICES[3][0]


class ShareProjectDataForm(ShareProjectDataWorkflowStep):
    workflow: ShareProjectDataWorkflow
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

    def __init__(self, workflow: ShareProjectDataWorkflow) -> None:
        super().__init__(workflow=workflow)
        self.project: models.Project | None = None
        self.paths: list[str] = []
        self.data_paths: list[models.DataPath] = []
        self.recipient_emails: list[str] = []

    @classmethod
    def build(cls, workflow: ShareProjectDataWorkflow, session: SyncSession) -> Self:
        project = session.get_one(
            Q.project.select(id=workflow.project_id),
            options=[
                orm.selectinload(models.Project.owner),
                orm.selectinload(models.Project.data_paths),
                orm.selectinload(models.Project.share_token),
            ],
        )
        paths = parsing.filter_subpaths([data_path.path for data_path in project.data_paths])
        data_paths = [data_path for data_path in project.data_paths if data_path.path in paths]

        form = cls(workflow=workflow)
        form.project = project
        form.paths = paths
        form.data_paths = data_paths
        form._context["project"] = project
        current_user = getattr(ctx.request.state, "current_user", None)
        if current_user is not None and not current_user.is_insider:
            form.custom_email.read_only = True
        return form

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            workflow: ShareProjectDataWorkflow = Depends(ShareProjectDataWorkflow.Init(cls.__name__)),
            session: SyncSession = Depends(dependencies.db_session),
        ) -> ShareProjectDataForm:
            return cls.build(workflow, session)
        return dependency

    def _collect_recipients(self, current_user: models.User) -> None:
        assert self.project is not None

        if not current_user.is_insider and self.time_valid_min.data > DEFAULT_TIME_VALID_MIN:
            self.add_general_error(
                f"You don't have permissions to create a link that lasts more than {DEFAULT_TIME_VALID_MIN} minutes."
            )
            return

        if not current_user.is_insider and self.custom_email.data:
            self.add_general_error("You don't have permissions to send to custom email addresses.")
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

    @htmx_route("POST")
    def Submit(cls) -> RouteFunc:
        def route(
            form: ShareProjectDataForm = Depends(ShareProjectDataForm.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_user),
            mailer: Mailer = Depends(dependencies.mail_client),
            _=Depends(dependencies.audit_log),
        ) -> Response:
            form._collect_recipients(current_user)
            form.assert_valid()

            assert form.project is not None
            project = form.project

            if (share_token := project.share_token) is not None:
                if not share_token._expired:
                    share_token._expired = True
                    session.save(share_token)

            share_token = session.save(Q.share_token.create(
                owner=current_user,
                time_valid_min=form.time_valid_min.data,
                paths=form.paths,
            ), flush=True)

            if form.mark_project_delivered.data:
                project.status = C.ProjectStatus.DELIVERED

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
                    )
                except smtplib.SMTPException as e:
                    logger.error(f"Failed to send email to {form.recipient_emails}: {e}")
                    raise
            else:
                logger.info(f"Email would be sent to: {form.recipient_emails}")

            for seq_request in project.seq_requests:
                for link in seq_request.delivery_email_links:
                    if link.email in form.recipient_emails:
                        link.status = C.DeliveryStatus.DISPATCHED
                        session.save(seq_request)

            return form.workflow.complete_to_project()
        return route
