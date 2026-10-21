import os

from fastapi import Depends, Query

from opengsync_db import queries as Q, SyncSession, models

from ...core.mailer import Mailer
from ...core import dependencies, exceptions as exc, responses, config
from ...components import inputs
from ..HTMXForm import HTMXForm, RouteFunc, FormFunc, htmx_route
from ..SubHTMXForm import SubHTMXForm
from ..common import SelectedPathsMixin, SelectedPathSubForm


TIME_VALID_CHOICES = [
    (60 * 24, "24 Hours"),
    (60 * 72, "3 Days"),
    (60 * 24 * 7, "1 Week"),
    (60 * 24 * 14, "2 Week"),
    (60 * 24 * 30, "1 Month"),
]

# SharePath.path is a String(512)
MAX_SHARE_PATH_LENGTH = 512


class RecipientSubForm(SubHTMXForm):
    email = inputs.string.EmailInputField("Recipient", placeholder="name@example.com")


def _resolve_share_path(share_root: str, path: str) -> str:
    """The real path of `path`, relative to the share root. Raises ValueError with the field's error message."""
    p = os.path.join(share_root, path)
    if not os.path.exists(p):
        raise ValueError("No longer exists on the share: it was probably moved or deleted recently. Remove it and try again.")

    relative = os.path.relpath(os.path.realpath(p), os.path.realpath(share_root))
    if relative == os.pardir or relative.startswith(os.pardir + os.sep) or os.path.isabs(relative):
        raise ValueError("Path is outside of share root.")
    if relative == os.curdir:
        raise ValueError("The share root itself cannot be shared.")
    if len(relative) > MAX_SHARE_PATH_LENGTH:
        raise ValueError(f"Path is longer than {MAX_SHARE_PATH_LENGTH} characters.")
    return relative


class SharePathAction(HTMXForm, SelectedPathsMixin):
    """Shares files and folders under the share root by email: one token holding all paths."""
    template_path = "actions/share-path.html"

    paths = inputs.dynamic.SubFormList[SelectedPathSubForm](min_elements=1)
    time_valid_min = inputs.selectable.SelectableInputField(
        "Link Validity Period",
        TIME_VALID_CHOICES,
        default=TIME_VALID_CHOICES[3][0],
    )
    recipients = inputs.dynamic.SubFormList[RecipientSubForm](min_elements=1)
    anonymous_send = inputs.boolean.CheckboxInputField("Anonymous Send")

    def __init__(self, initial_paths: list[str] | None = None, from_selection: bool = False) -> None:
        super().__init__()
        self.initial_paths = initial_paths or []
        # Opened from the file browser's selection panel: a successful share clears that selection
        self.from_selection = from_selection
        self.post_url = responses.url_for(f"{self.__class__.__name__}.Submit")
        if from_selection:
            self.post_url = self.post_url.include_query_params(from_selection="true")
        # Blank row the + button clones (private, so it is not validated as a sub-form).
        self._recipient_template = RecipientSubForm(prefix=f"{self.recipients.name}-__INDEX__")

    @property
    def recipient_template(self) -> RecipientSubForm:
        return self._recipient_template

    @classmethod
    def Init(cls) -> FormFunc:
        def dependency(
            path: list[str] = Query(default=[]),
            from_selection: bool = False,
        ) -> "SharePathAction":
            return SharePathAction(initial_paths=path, from_selection=from_selection)
        return dependency

    def prepare(self) -> None:
        self.prefill_paths(self.initial_paths)
        self.recipients.append_entry()

    @htmx_route("GET", "/share-path")
    def Begin(cls) -> RouteFunc:
        def route(
            form: "SharePathAction" = Depends(SharePathAction.Init()),
            _=Depends(dependencies.require_data_assigner),
        ):
            return form.make_response()
        return route

    @htmx_route("POST", "/share-path")
    def Submit(cls) -> RouteFunc:
        def route(
            form: "SharePathAction" = Depends(SharePathAction.Validate()),
            session: SyncSession = Depends(dependencies.db_session),
            current_user: models.User = Depends(dependencies.require_data_assigner),
            mailer: Mailer = Depends(dependencies.mail_client),
        ):
            # As legacy's SelectField: only the offered validity periods
            if form.time_valid_min.data not in dict(TIME_VALID_CHOICES):
                form.time_valid_min.errors.append("Not a valid choice.")
                raise exc.FormValidationException(form)

            form.assert_path_count()

            # Each address is validated by its EmailInputField, and min_elements requires at least one.
            recipients = [entry.email.data for entry in form.recipients]

            # Any invalid path rejects the whole share, so nothing is half-shared
            share_root = config.settings.app_config.share_root
            share_paths: list[str] = []
            for entry in form.paths:
                try:
                    share_paths.append(_resolve_share_path(share_root, entry.path.data))
                except ValueError as e:
                    entry.path.errors.append(str(e))
            if form.paths.has_errors:
                raise exc.FormValidationException(form)

            # A folder already shares everything below it
            share_paths = form.collapse_paths(share_paths)

            share_token = session.save(Q.share_token.create(
                owner=current_user,
                time_valid_min=form.time_valid_min.data,
                paths=share_paths,
            ), flush=True)

            # Send email
            browse_link = str(responses.external_url_for("file_share.browse", token=share_token.uuid))
            mailer.send_share_paths(
                recipients=list(set(recipients)),
                share_token=share_token,
                author=None if form.anonymous_send.data else current_user,
                browse_link=browse_link,
            )

            return responses.htmx_response(
                flash=responses.flash("Email Sent!", "success"),
            )
        return route
