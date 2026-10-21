from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import SyncSession, models

from ...core import dependencies, responses, secrets, column_values, exceptions as exc

router = APIRouter(prefix="/column-values", tags=["column-values"])


def column_value_viewer(
    token: str | None = Query(None, description="Registration or activation token of a user who is not logged in"),
    current_user: models.User | None = Depends(dependencies.get_user),
) -> models.User | None:
    """The logged-in user, or None for the holder of a valid registration/activation token (who fills in their
    profile before having an account to log in with)."""
    if current_user is not None:
        return current_user
    if token and (secrets.verify_registration_token(token) is not None or secrets.verify_activation_token(token) is not None):
        return None
    raise exc.NoPermissionsException("Log in or use a valid registration/activation link.")


@router.get("/{source}/search")
def search_column_values(
    request: Request,
    source: str,
    word: str | None = Query(None, description="Search word"),
    selected_id: str | None = Query(None, description="Key of the currently selected value"),
    page: int = Query(0, ge=0, description="Page number, starting from 0"),
    viewer: models.User | None = Depends(column_value_viewer),
    session: SyncSession = Depends(dependencies.db_session),
):
    column_source = column_values.SOURCES.get(source)
    if column_source is None:
        raise exc.NotFoundException(f"Unknown column value source '{source}'.")

    options, has_more = column_values.search(
        session, column_source,
        word=word.strip() if word else None,
        page=page,
        selected_id=selected_id,
        filters={name: request.query_params.get(name) for name in column_source.filters},
        show_description=not column_source.description_insiders_only or (viewer is not None and viewer.is_insider),
    )
    return responses.query_options_response(options, has_more=has_more)
