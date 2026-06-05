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
    checklist_type: LabChecklistType | None = None,
    service_type: ServiceType | None = None,
    checklist_type_in: Sequence[LabChecklistType] | None = None,
    service_type_in: Sequence[ServiceType] | None = None,
    search_name: str | None = None,
    search_creator_name: str | None = None,
    statement: sql.Select[tuple[LabPrep]] = sa.select(LabPrep),
) -> sql.Select[tuple[LabPrep]]:
    if id is not None:
        statement = statement.where(LabPrep.id == id)
    if status is not None:
        statement = statement.where(LabPrep.status_id == status.id)
    if status_in is not None:
        statement = statement.where(LabPrep.status_id.in_([s.id for s in status_in]))
    if creator is not None:
        statement = statement.where(LabPrep.creator_id == creator.id)
    if checklist_type is not None:
        statement = statement.where(LabPrep.checklist_type_id == checklist_type.id)
    if service_type is not None:
        statement = statement.where(LabPrep.service_type_id == service_type.id)
    if checklist_type_in is not None:
        statement = statement.where(LabPrep.checklist_type_id.in_([c.id for c in checklist_type_in]))
    if service_type_in is not None:
        statement = statement.where(LabPrep.service_type_id.in_([s.id for s in service_type_in]))

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