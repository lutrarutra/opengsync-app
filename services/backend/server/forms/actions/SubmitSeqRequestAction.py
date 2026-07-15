from fastapi import Depends

from opengsync_db import models, SyncSession, queries as Q, categories as C, actions

from ...core import dependencies, exceptions as exc, responses
from ...components import inputs
from ..HTMXForm import HTMXForm, FormFunc, RouteFunc, htmx_route


class SubmitSeqRequestAction(HTMXForm):
    template_path = "forms/seq_request/submit_request.html"

    sample_submission_time = inputs.datetime.DateTimepickerInputField("Sample Submission Time", required=False)
    samples_delivered_by_mail = inputs.boolean.CheckboxInputField("Samples are Delivered by Mail")
    custom_sample_submission_time = inputs.boolean.CheckboxInputField("We have agreed to a time that is outside the available submission windows.")
    comment = inputs.string.TextAreaInputField("Additional Comment for Submission", required=False, max_length=4096)

    def __init__(self, seq_request: models.SeqRequest):
        super().__init__()
        self.seq_request = seq_request

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            seq_request_id: int,
            session: SyncSession = Depends(dependencies.db_session),
            access_level: C.AccessLevel = Depends(dependencies.seq_request_permissions),
        ) -> "SubmitSeqRequestAction":
            seq_request = session.get_one(Q.seq_request.select(id=seq_request_id))
            if access_level < C.AccessLevel.WRITE:
                raise exc.NoPermissionsException("You do not have permission to submit this request.")
            if seq_request.status != C.SeqRequestStatus.DRAFT:
                raise exc.BadRequestException("Only draft requests can be submitted.")
            return cls(seq_request=seq_request)
        return dependency

    @htmx_route("GET", "/{seq_request_id}/submit", name="Submit")
    def Render(cls) -> RouteFunc:
        def route(form: "SubmitSeqRequestAction" = Depends(SubmitSeqRequestAction.Init())):
            return form.make_response()
        return route

    @htmx_route("POST", "/{seq_request_id}/submit", name="Submit")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SubmitSeqRequestAction" = Depends(SubmitSeqRequestAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_insider),
        ):
            if not form.seq_request.is_submittable() and not current_user.is_insider:
                raise exc.BadRequestException("Request is missing prerequisites for submission.")
            
            if form.sample_submission_time.data and form.samples_delivered_by_mail.data:
                form.sample_submission_time.errors.append("Select sample submission time or delivery by mail.")
                form.samples_delivered_by_mail.errors.append("Select sample submission time or delivery by mail.")
                raise exc.FormValidationException(form)

            if not form.sample_submission_time.data and not form.samples_delivered_by_mail.data:
                form.sample_submission_time.errors.append("Select sample submission time or delivery by mail.")
                form.samples_delivered_by_mail.errors.append("Select sample submission time or delivery by mail.")
                raise exc.FormValidationException(form)

            if form.comment.data and (comment := form.comment.data.strip()):
                session.save(
                    Q.comment.create(
                        seq_request_id=form.seq_request.id,
                        author=current_user,
                        text=f"Sample submission comment: {comment}",
                    )
                )

            seq_request = actions.submit_seq_request(session=session, seq_request=form.seq_request)

            return responses.htmx_response(
                redirect=responses.url_for("seq_request_page", seq_request_id=seq_request.id),
                flash=responses.flash("Sequencing request submitted successfully.", "success"),
            )
        return route
