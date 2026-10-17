"""Pages of options for spreadsheet QueryColumns (components/tables/spreadsheet.py), searched in several columns,
and for SearchableInputFields (``search_response`` with the ``*_option`` functions below).

Rows containing the word in any of the search columns come first, then rows similar to it in any of them (typos),
each ordered by their best similarity. The search columns per kind of object are:

- kits (index, feature, any): name and identifier, shown as "[identifier] name"
- projects: title and identifier
- libraries: name and sample name, shown by name
- samples and protocols: name
"""
from typing import Any, Callable, Sequence

import sqlalchemy as sa
from fastapi.responses import Response

from opengsync_db import SyncSession, models, utils, categories as C

from . import responses

QUERY_PAGE_SIZE = 20

KIT_SEARCH_COLUMNS = (models.Kit.name, models.Kit.identifier)
PROJECT_SEARCH_COLUMNS = (models.Project.title, models.Project.identifier)
LIBRARY_SEARCH_COLUMNS = (models.Library.name, models.Library.sample_name)
SAMPLE_SEARCH_COLUMNS = (models.Sample.name,)
PROTOCOL_SEARCH_COLUMNS = (models.Protocol.name,)


def kit_label(kit: models.Kit) -> str:
    return f"[{kit.identifier}] {kit.name}"


def search(stmt: sa.Select, columns: Sequence[Any], word: str | None, order_column: Any) -> sa.Select:
    """Filter and order ``stmt`` by ``word`` in ``columns``, only ordered by ``order_column`` without a word."""
    if not word:
        return stmt.order_by(order_column.asc())
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    contains = sa.or_(*(column.ilike(f"%{escaped}%", escape="\\") for column in columns))
    similar = sa.or_(*(utils.safe_trgm_search(column, word) for column in columns))
    similarities = [sa.func.coalesce(sa.func.similarity(column, word), 0) for column in columns]
    similarity = similarities[0] if len(similarities) == 1 else sa.func.greatest(*similarities)
    return stmt.where(sa.or_(contains, similar)).order_by(
        sa.case((contains, 0), else_=1), similarity.desc(), order_column.asc(),
    )


def options_response(
    session: SyncSession,
    stmt: sa.Select,
    *,
    columns: Sequence[Any],
    word: str | None,
    page: int,
    order_column: Any,
    label: Callable[[Any], str],
) -> Response:
    """A page of the rows of ``stmt`` matching ``word``, as ``responses.query_options_response``."""
    objects, count = session.page(search(stmt, columns, word, order_column), page=page, limit=QUERY_PAGE_SIZE)
    return responses.query_options_response(
        ((obj.id, label(obj)) for obj in objects),
        has_more=(page + 1) * QUERY_PAGE_SIZE < count,
    )


def search_response(
    session: SyncSession,
    stmt: sa.Select,
    *,
    page: int,
    option: Callable[[Any], responses.QueryOption],
    load: utils.QueryOptions | None = None,
) -> Response:
    """A page of the rows of ``stmt``, filtered and ordered by the search route, for a SearchableInputField."""
    objects, count = session.page(stmt, page=page, limit=QUERY_PAGE_SIZE, options=load)
    return responses.query_options_response(
        (option(obj) for obj in objects),
        has_more=(page + 1) * QUERY_PAGE_SIZE < count,
    )


def _option(
    id: int, name: str, header: str | None = None, description: str | None = None, data: dict[str, Any] | None = None,
) -> responses.QueryOption:
    option: responses.QueryOption = {"id": id, "name": name}
    if header:
        option["header"] = header
    if description:
        option["description"] = description
    if data:
        option["data"] = data
    return option


def _clone_suffix(clone_number: int) -> str:
    return f" (re:{clone_number})" if clone_number > 0 else ""


def project_option(project: models.Project) -> responses.QueryOption:
    return _option(project.id, project.title, project.identifier, f"{project.status.label} {project.status.icon}")


def user_option(user: models.User) -> responses.QueryOption:
    return _option(user.id, user.name, user.role.icon, user.email, data={"email": user.email})


def group_option(group: models.Group) -> responses.QueryOption:
    return _option(group.id, group.name, description=f"{group.type.label} {group.type.icon}")


def pool_option(pool: models.Pool) -> responses.QueryOption:
    return _option(pool.id, pool.name + _clone_suffix(pool.clone_number), description=f"{pool.status.label} {pool.status.icon}")


def library_option(library: models.Library) -> responses.QueryOption:
    flags = library.type.abbreviation
    if library.seq_request and library.seq_request.submission_type == C.SubmissionType.QC_ONLY:
        flags += " [qc]"
    if library.mux_type:
        flags += f" [{library.mux_type.abbreviation}]"
    if library.nuclei_isolation:
        flags += " [ncl]"
    return _option(library.id, library.name + _clone_suffix(library.clone_number), description=flags)


def seq_request_option(seq_request: models.SeqRequest) -> responses.QueryOption:
    return _option(
        seq_request.id, seq_request.name, f"{seq_request.status.icon} {seq_request.status.label}",
        seq_request.submission_type.abbreviation,
    )


def experiment_option(experiment: models.Experiment) -> responses.QueryOption:
    return _option(
        experiment.id, experiment.name, f"{experiment.status.icon} {experiment.status.label}", experiment.workflow.name,
    )


def sequencer_option(sequencer: models.Sequencer) -> responses.QueryOption:
    return _option(sequencer.id, sequencer.name, description=f"{sequencer.model.manufacturer} {sequencer.model.label}")


def kit_option(kit: models.Kit) -> responses.QueryOption:
    # Kits of a specific kind (e.g. index kits) have a type of their own
    kind = getattr(kit, "type", None)
    description = f"{kind.label} Kit" if kind is not None else kit.kit_type.label
    return _option(kit.id, kit.name, kit.identifier, description)
