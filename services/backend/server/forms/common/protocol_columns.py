"""Spreadsheet QueryColumn selecting protocols by id, searched by name (core/query_options.py)."""
from typing import Sequence

import sqlalchemy as sa

from opengsync_db import models, queries as Q

from ...components.tables.spreadsheet import QueryColumn
from ...core import responses
from ...core.context import ctx


def _names(ids: Sequence[int]) -> dict[int, str]:
    stmt = Q.protocol.select().where(models.Protocol.id.in_(ids))
    return {protocol.id: protocol.name for protocol in ctx.session.get_all(stmt, limit=None)}


def _resolve(texts: Sequence[str]) -> dict[str, int]:
    """Texts naming exactly one protocol (ignoring case)."""
    keys = {text: text.strip().lower() for text in texts}
    stmt = Q.protocol.select().where(sa.func.lower(models.Protocol.name).in_(sorted(set(keys.values()))))
    matches: dict[str, set[int]] = {}
    for protocol in ctx.session.get_all(stmt, limit=None):
        matches.setdefault(protocol.name.lower(), set()).add(protocol.id)
    return {text: next(iter(matches[key])) for text, key in keys.items() if len(matches.get(key, ())) == 1}


def protocol_column(label: str, name: str, width: float, required: bool = False, read_only: bool = False) -> QueryColumn:
    return QueryColumn(
        label, name, width, required=required, read_only=read_only,
        url=lambda: responses.url_for("query_protocols"), lookup=_names, resolve=_resolve,
    )
