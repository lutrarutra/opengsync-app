from typing import Sequence
import sqlalchemy as sa
from sqlalchemy import sql


from ..models import User, LabPrep
from ..categories import PrepStatus, LabChecklistType, ServiceType

def create(
    name: str,
    creator: User,
    number: int,
    checklist_type: LabChecklistType,
    service_type: ServiceType,
) -> LabPrep:
    return LabPrep(
        name=name,
        creator_id=creator.id,
        prep_number=number,
        checklist_type_id=checklist_type.id,
        service_type_id=service_type.id,
    )


def select(
    id: int | None = None,
    status: PrepStatus | None = None,
    status_in: list[PrepStatus] | None = None,
    creator: User | None = None,
    creator_id: int | None = None,
    checklist_type: LabChecklistType | None = None,
    service_type: ServiceType | None = None,
    checklist_type_in: Sequence[LabChecklistType] | None = None,
    service_type_in: Sequence[ServiceType] | None = None,
    search_name: str | None = None,
    search_creator_name: str | None = None,
    statement: sql.Select[tuple[LabPrep]] = sa.select(LabPrep),
) -> sql.Select[tuple[LabPrep]]:
    statement = statement.where(*where_clauses(
        id=id,
        status=status,
        status_in=status_in,
        creator=creator,
        creator_id=creator_id,
        checklist_type=checklist_type,
        service_type=service_type,
        checklist_type_in=checklist_type_in,
        service_type_in=service_type_in,
    ))

    if search_name is not None:
        statement = statement.order_by(sa.func.similarity(LabPrep.name, search_name).desc())
    elif search_creator_name is not None:
        statement = statement.join(
            User,
            User.id == LabPrep.creator_id
        ).order_by(
            sa.func.similarity(User.first_name + ' ' + User.last_name, search_creator_name).desc()
        )
    return statement


def where_clauses(
    id: int | None = None,
    status: PrepStatus | None = None,
    status_in: list[PrepStatus] | None = None,
    creator: User | None = None,
    creator_id: int | None = None,
    checklist_type: LabChecklistType | None = None,
    service_type: ServiceType | None = None,
    checklist_type_in: Sequence[LabChecklistType] | None = None,
    service_type_in: Sequence[ServiceType] | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering lab preps.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(LabPrep.id == id)
    if status is not None:
        clauses.append(LabPrep.status_id == status.id)
    if status_in is not None:
        clauses.append(LabPrep.status_id.in_([s.id for s in status_in]))
    if creator is not None:
        clauses.append(LabPrep.creator_id == creator.id)
    if creator_id is not None:
        clauses.append(LabPrep.creator_id == creator_id)
    if checklist_type is not None:
        clauses.append(LabPrep.checklist_type_id == checklist_type.id)
    if service_type is not None:
        clauses.append(LabPrep.service_type_id == service_type.id)
    if checklist_type_in is not None:
        clauses.append(LabPrep.checklist_type_id.in_([c.id for c in checklist_type_in]))
    if service_type_in is not None:
        clauses.append(LabPrep.service_type_id.in_([s.id for s in service_type_in]))

    return clauses