import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, SeqRequest, Project, Sample, Library, links, Contact, Group
from ..categories import (
    SeqRequestStatus, DataDeliveryMode, ReadType,
    SubmissionType, UserRole, LibraryType, AccessLevel
)

def create(
    name: str,
    description: str | None,
    requestor: User,
    group: Group | None,
    billing_contact: Contact,
    data_delivery_mode: DataDeliveryMode,
    read_type: ReadType,
    submission_type: SubmissionType,
    contact_person: Contact,
    organization_contact: Contact,
    bioinformatician_contact: Contact | None = None,
    read_length: int | None = None,
    num_lanes: int | None = None,
    special_requirements: str | None = None,
    billing_code: str | None = None,
) -> SeqRequest:
    return SeqRequest(
        name=name.strip(),
        group=group,
        description=description.strip() if description else None,
        requestor=requestor,
        read_length=read_length,
        num_lanes=num_lanes,
        read_type_id=read_type.id,
        special_requirements=special_requirements,
        billing_contact=billing_contact,
        submission_type_id=submission_type.id,
        contact_person=contact_person,
        organization_contact=organization_contact,
        bioinformatician_contact=bioinformatician_contact,
        status_id=SeqRequestStatus.DRAFT.id,
        data_delivery_mode_id=data_delivery_mode.id,
        billing_code=billing_code.strip() if billing_code else None,
    )


def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(
        User.id == user_id,
        User.role_id == UserRole.ADMIN.id
    )

    is_insider = sa.select(1).where(
        User.id == user_id,
        User.role_id.in_([UserRole.BIOINFORMATICIAN.id, UserRole.TECHNICIAN.id])
    )

    has_write_access = sa.and_(
        SeqRequest.status_id == SeqRequestStatus.DRAFT.id,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.exists().where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            )
        )
    )

    has_read_access = sa.or_(
        SeqRequest.requestor_id == user_id,
        sa.exists().where(
            (links.UserAffiliation.user_id == user_id) &
            (links.UserAffiliation.group_id == SeqRequest.group_id)
        )
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (has_write_access, AccessLevel.WRITE),
        (has_read_access, AccessLevel.READ),
        else_=AccessLevel.NONE
    )


def select(
    id: int | None = None,
    status: SeqRequestStatus | None = None,
    status_in: list[SeqRequestStatus] | None = None,
    submission_type: SubmissionType | None = None,
    submission_type_in: list[SubmissionType] | None = None,
    library_types_in: list[LibraryType] | None = None,
    show_drafts: bool = True, user_id: int | None = None,
    project_id: int | None = None,
    group_id: int | None = None,
    viewer_id: int | None = None,
    search_name: str | None = None,
    search_requestor_name: str | None = None,
    search_group_name: str | None = None,
    statement: sql.Select[tuple[SeqRequest]] = sa.select(SeqRequest),
) -> sql.Select[tuple[SeqRequest]]:
    if id is not None:
        statement = statement.where(SeqRequest.id == id)
    if status is not None:
        statement = statement.where(
            SeqRequest.status_id == status.id
        )

    if submission_type is not None:
        statement = statement.where(
            SeqRequest.submission_type_id == submission_type.id
        )

    if user_id is not None:
        statement = statement.where(
            sa.or_(
                SeqRequest.requestor_id == user_id,
                sa.exists().where(
                    (links.UserAffiliation.user_id == user_id) &
                    (links.UserAffiliation.group_id == SeqRequest.group_id)
                ),
            )
        )

    if status_in is not None:
        status_ids = [status.id for status in status_in]
        statement = statement.where(
            SeqRequest.status_id.in_(status_ids)  # type: ignore
        )
    
    if submission_type_in is not None:
        submission_type_ids = [submission_type.id for submission_type in submission_type_in]
        statement = statement.where(
            SeqRequest.submission_type_id.in_(submission_type_ids)  # type: ignore
        )

    if library_types_in is not None:
        statement = statement.where(
            sa.exists().where(
                (Library.seq_request_id == SeqRequest.id) &
                (Library.type_id.in_([lt.id for lt in library_types_in]))  # type: ignore
            )
        )

    if not show_drafts:
        statement = statement.where(
            sa.or_(
                SeqRequest.status_id != SeqRequestStatus.DRAFT.id,
                SeqRequest.requestor_id == user_id
            )
        )

    if group_id is not None:
        statement = statement.where(SeqRequest.group_id == group_id)

    if project_id is not None:
        statement = statement.where(
            sa.exists().where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == SeqRequest.id) &
                (Project.id == project_id)
            )
        )
    if viewer_id is not None:
        statement = statement.where(access_level(viewer_id) >= AccessLevel.READ)

    if search_name is not None:
        statement = statement.order_by(sa.func.similarity(SeqRequest.name, search_name).desc())
    if search_requestor_name is not None:
        statement = statement.join(User, SeqRequest.requestor_id == User.id).order_by(
            sa.func.similarity(User.name, search_requestor_name).desc()
        )
    if search_group_name is not None:
        statement = statement.join(Group, SeqRequest.group_id == Group.id).order_by(
            sa.func.similarity(Group.name, search_group_name).desc()
        )
    return statement

def permissions(seq_request_id: int, user_id: int) -> sql.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(SeqRequest.id == seq_request_id)