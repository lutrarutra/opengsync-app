from fastapi import APIRouter, Depends, Query, Request

from webauthn.helpers import bytes_to_base64url

from opengsync_db import models, SyncSession, queries as Q

from ...core import dependencies, exceptions as exc, passkeys, responses

router = APIRouter(prefix="/passkeys", tags=["passkeys"], dependencies=[Depends(dependencies.audit_log)])


def _render_list(request: Request, session: SyncSession, user: models.User, current_user: models.User, **kwargs):
    user_passkeys = session.get_all(
        Q.passkey.select(user_id=user.id), order_by=models.UserPasskey.created_utc.asc(), limit=None,
    )
    return responses.htmx_response(
        template="components/passkey-list.html",
        user=user,
        passkeys=user_passkeys,
        is_owner=current_user.id == user.id,
        rp_id=passkeys.rp_id(request),
        user_handle=bytes_to_base64url(user.webauthn_user_handle) if user.webauthn_user_handle else None,
        credential_ids=[bytes_to_base64url(p.credential_id) for p in user_passkeys],
        **kwargs,
    )


@router.get("/list")
def render_passkey_list(
    request: Request,
    user_id: int = Query(..., description="Owner of the passkeys"),
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    if current_user.id != user_id and not current_user.is_admin:
        raise exc.NoPermissionsException("You do not have permission to view this user's passkeys.")

    user = session.get_one(Q.user.select(id=user_id))
    return _render_list(request, session, user, current_user)


@router.delete("/{passkey_id}")
def delete_passkey(
    request: Request,
    passkey_id: int,
    current_user: models.User = Depends(dependencies.require_user),
    session: SyncSession = Depends(dependencies.db_session),
):
    passkey = session.get_one(Q.passkey.select(id=passkey_id))
    if passkey.user_id != current_user.id and not current_user.is_admin:
        raise exc.NoPermissionsException("You do not have permission to delete this passkey.")

    user = passkey.user
    session.delete(passkey, flush=True)
    return _render_list(request, session, user, current_user, flash=responses.flash("Passkey removed.", "success"))
