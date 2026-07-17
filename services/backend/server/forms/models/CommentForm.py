from fastapi import Query, Depends
from fastapi.responses import Response

from opengsync_db import queries as Q, SyncSession, models, categories as C

from ...core import responses, exceptions as exc, dependencies
from ...components import inputs
from ..HTMXForm import RouteFunc, FormFunc, htmx_route, HTMXForm


class CommentForm(HTMXForm):
    template_path = "forms/comment.html"

    comment = inputs.string.TextAreaInputField("Comment", required=True, max_length=4096)

    def __init__(
        self,
        seq_request_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
    ) -> None:
        super().__init__()
        self.seq_request_id = seq_request_id
        self.experiment_id = experiment_id
        self.lab_prep_id = lab_prep_id
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit").include_query_params(**{
            k: v for k, v in {
                "seq_request_id": seq_request_id,
                "experiment_id": experiment_id,
                "lab_prep_id": lab_prep_id,
            }.items() if v is not None
        })

    @classmethod
    def Init(cls) -> FormFunc:
        def form(
            seq_request_id: int | None = Query(None),
            experiment_id: int | None = Query(None),
            lab_prep_id: int | None = Query(None),
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
        ):
            form = CommentForm(
                seq_request_id=seq_request_id,
                experiment_id=experiment_id,
                lab_prep_id=lab_prep_id,
            )
            if form.seq_request_id is not None:
                if session.get_access_level(Q.seq_request.permissions(seq_request_id=form.seq_request_id, user_id=current_user.id)) < C.AccessLevel.WRITE:
                    raise exc.NoPermissionsException("You do not have permission to comment on this sequencing request.")
            elif form.experiment_id is not None or form.lab_prep_id is not None:
                if not current_user.is_insider:
                    raise exc.NoPermissionsException("You do not have permission to comment on this resource.")
            else:
                raise exc.BadRequestException("At least one of seq_request_id, experiment_id, or lab_prep_id must be provided.")
            return form
        return form
    
    @htmx_route("GET", "/comment")
    def Begin(cls) -> RouteFunc:
        def route(form: CommentForm = Depends(CommentForm.Init())) -> Response:
            return form.make_response()
        return route

    @htmx_route("POST", "/comment")
    def Submit(cls) -> RouteFunc:
        def route(
            current_user: models.User = Depends(dependencies.require_user),
            session: SyncSession = Depends(dependencies.db_session),
            form: CommentForm = Depends(CommentForm.Validate()),
        ) -> Response:
            """Process the comment form submission."""
            comment = Q.comment.create(
                text=form.comment.data,
                author=current_user,
                seq_request_id=form.seq_request_id,
                experiment_id=form.experiment_id,
                lab_prep_id=form.lab_prep_id,
            )
            session.add(comment)

            if form.seq_request_id is not None:
                redirect = responses.url_for("seq_request_page", seq_request_id=form.seq_request_id).include_query_params(tab="request-comments-tab")
            elif form.experiment_id is not None:
                redirect = responses.url_for("experiment_page", experiment_id=form.experiment_id).include_query_params(tab="experiment-comments-tab")
            elif form.lab_prep_id is not None:
                redirect = responses.url_for("lab_prep", lab_prep_id=form.lab_prep_id).include_query_params(tab="comments-tab")
            else:
                redirect = responses.url_for("dashboard")

            return responses.htmx_response(
                redirect=redirect,
                flash=responses.flash("Comment Added!", "success"),
            )
        return route