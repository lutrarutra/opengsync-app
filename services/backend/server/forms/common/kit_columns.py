"""Spreadsheet QueryColumns selecting kits by id, searched by name or identifier (core/query_options.py).

Forms keep working with kit identifiers downstream: ``kit_identifiers`` names the ids of a validated column and
``kit_ids`` resolves stored identifiers back to ids when a step is shown again.
"""
import json
from typing import Any, Callable, Iterable, Sequence

import pandas as pd
import sqlalchemy as sa

from opengsync_db import models, categories as C, queries as Q

from ...components.tables.spreadsheet import QueryColumn
from ...core import responses
from ...core.context import ctx


def _label(kit: models.Kit) -> str:
    return f"[{kit.identifier}] {kit.name}"


def _lookup(select: Callable[[], sa.Select]) -> Callable[[Sequence[int]], dict[int, str]]:
    def lookup(ids: Sequence[int]) -> dict[int, str]:
        stmt = select().where(models.Kit.id.in_(ids))
        return {kit.id: _label(kit) for kit in ctx.session.get_all(stmt, limit=None)}
    return lookup


def _resolve(select: Callable[[], sa.Select]) -> Callable[[Sequence[str]], dict[str, int]]:
    """Texts naming exactly one kit: its identifier, "[identifier] name" or its name (ignoring case)."""
    def resolve(texts: Sequence[str]) -> dict[str, int]:
        keys = {text: text.strip().lower() for text in texts}
        values = sorted(set(keys.values()))
        stmt = select().where(sa.or_(
            sa.func.lower(models.Kit.identifier).in_(values),
            sa.func.lower(models.Kit.name).in_(values),
            sa.func.lower("[" + models.Kit.identifier + "] " + models.Kit.name).in_(values),
        ))
        matches: dict[str, set[int]] = {}
        for kit in ctx.session.get_all(stmt, limit=None):
            for key in {kit.identifier.lower(), kit.name.lower(), _label(kit).lower()}:
                matches.setdefault(key, set()).add(kit.id)
        return {
            text: next(iter(matches[key])) for text, key in keys.items() if len(matches.get(key, ())) == 1
        }
    return resolve


def _type_in(types: Iterable[Any]) -> dict[str, str]:
    return {"type_in": json.dumps([t.id for t in types])}


def feature_kit_column(
    label: str, name: str, width: float, types: Sequence[C.FeatureType], required: bool = False, read_only: bool = False,
) -> QueryColumn:
    """Feature kits of one of ``types``."""
    return QueryColumn(
        label, name, width, required=required, read_only=read_only,
        lookup=_lookup(lambda: Q.feature_kit.select(type_in=list(types))),
        resolve=_resolve(lambda: Q.feature_kit.select(type_in=list(types))),
        url=lambda: responses.url_for("query_feature_kits").include_query_params(**_type_in(types)),
    )


def index_kit_column(
    label: str, name: str, width: float, types: Sequence[C.IndexType], required: bool = False, read_only: bool = False,
) -> QueryColumn:
    """Index kits of one of ``types``."""
    return QueryColumn(
        label, name, width, required=required, read_only=read_only,
        lookup=_lookup(lambda: Q.index_kit.select(type_in=list(types))),
        resolve=_resolve(lambda: Q.index_kit.select(type_in=list(types))),
        url=lambda: responses.url_for("query_index_kits").include_query_params(**_type_in(types)),
    )


def kit_column(label: str, name: str, width: float, required: bool = False, read_only: bool = False) -> QueryColumn:
    """Kits of every type."""
    return QueryColumn(
        label, name, width, required=required, read_only=read_only,
        lookup=_lookup(lambda: Q.kit.select()),
        resolve=_resolve(lambda: Q.kit.select()),
        url=lambda: responses.url_for("query_kits"),
    )


def kit_identifiers(ids: Iterable[Any]) -> dict[int, str]:
    """Identifiers of the kits with the given ids (empty cells are skipped)."""
    kit_ids = sorted({int(kit_id) for kit_id in ids if pd.notna(kit_id)})
    if not kit_ids:
        return {}
    stmt = Q.kit.select().where(models.Kit.id.in_(kit_ids))
    return {kit.id: kit.identifier for kit in ctx.session.get_all(stmt, limit=None)}


def kit_ids(identifiers: Iterable[Any]) -> dict[str, int]:
    """Ids of the kits with the given identifiers (empty cells are skipped)."""
    names = sorted({str(identifier) for identifier in identifiers if pd.notna(identifier)})
    if not names:
        return {}
    stmt = Q.kit.select().where(models.Kit.identifier.in_(names))
    return {kit.identifier: kit.id for kit in ctx.session.get_all(stmt, limit=None)}


def identifiers_column(df: pd.DataFrame, id_column: str) -> pd.Series:
    """The identifiers of the kit ids in ``df[id_column]``, None for empty cells."""
    mapping = kit_identifiers(df[id_column])
    return df[id_column].map(lambda kit_id: mapping.get(int(kit_id)) if pd.notna(kit_id) else None).astype(object)


def ids_column(df: pd.DataFrame, identifier_column: str) -> pd.Series:
    """The kit ids of the identifiers in ``df[identifier_column]``, <NA> for empty or unknown identifiers."""
    if identifier_column not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype=pd.Int64Dtype())
    mapping = kit_ids(df[identifier_column])
    return df[identifier_column].map(lambda identifier: mapping.get(str(identifier)) if pd.notna(identifier) else None).astype(pd.Int64Dtype())
