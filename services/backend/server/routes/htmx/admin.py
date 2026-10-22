import os

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query, Request

from opengsync_db import models, SyncSession

from ...core import dependencies, responses, config, audit_reader, exceptions as exc
from ...chat import usage as chat_usage

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(dependencies.require_admin)])

CHAT_USAGE_DAYS = (7, 30, 90)


@router.get("/chat-usage", name="admin_chat_usage")
def get_chat_usage(
    days: int = Query(30),
    session: SyncSession = Depends(dependencies.db_session),
):
    if days not in CHAT_USAGE_DAYS:
        raise exc.BadRequestException(f"days must be one of {', '.join(map(str, CHAT_USAGE_DAYS))}.")

    audit_folder = os.path.join(config.settings.app_config.log_folder, "audits")
    summary = chat_usage.summarize(audit_folder, now=config.settings.now(), days=days)

    user_ids = {u.user_id for u in summary.top_users} | {m.user_id for m in summary.recent}
    user_ids.discard(None)
    users = {
        user.id: user for user in session.get_all(sa.select(models.User).where(models.User.id.in_(user_ids)), limit=None)
    } if user_ids else {}

    return responses.htmx_response(
        template="components/admin/chat-usage.html",
        usage=summary, users=users, day_options=CHAT_USAGE_DAYS,
        chat_enabled=config.settings.app_config.chat.enabled,
    )


@router.get("/audits", name="admin_audit_log")
def get_audit_log(
    request: Request,
    page: int = Query(0, ge=0),
    session: SyncSession = Depends(dependencies.db_session),
):
    try:
        flt = audit_reader.parse_filter(dict(request.query_params), today=config.settings.now().date())
    except ValueError as e:
        raise exc.BadRequestException(str(e))
    audit_folder = os.path.join(config.settings.app_config.log_folder, "audits")
    result = audit_reader.query(audit_folder, flt, tz=config.settings.TIMEZONE, page=page)

    user_ids = {e.user_id for e in result.entries} | {e.owner_id for e in result.entries}
    if flt.user_id is not None:
        user_ids.add(flt.user_id)
    user_ids.discard(None)
    users = {
        user.id: user for user in session.get_all(sa.select(models.User).where(models.User.id.in_(user_ids)), limit=None)
    } if user_ids else {}

    filters = {k: v for k, v in request.query_params.items() if k in audit_reader.FILTERS and v.strip()}
    return responses.htmx_response(
        template="components/admin/audit-log.html",
        result=result, flt=flt, filters=filters, users=users,
    )
