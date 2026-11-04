import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, SeqRequest, Group, Sample, Library, links, Contact, OperationRun
from ..categories import (
    SeqRequestStatus, DataDeliveryMode, ReadType,
    SubmissionType, LibraryType, AccessLevel, AffiliationType
)
from ..core import utils

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
    pi_contact: Contact | None = None,
) -> SeqRequest:
    return SeqRequest(
        name=name.strip(),
        group=group,
        description=description.strip() if description else None,
        requestor=requestor,
        read_length=read_length,
        num_lanes=num_lanes,
        read_type=read_type,
        special_requirements=special_requirements,
        billing_contact=billing_contact,
        submission_type=submission_type,
        contact_person=contact_person,
        organization_contact=organization_contact,
        bioinformatician_contact=bioinformatician_contact,
        status=SeqRequestStatus.DRAFT,
        data_delivery_mode=data_delivery_mode,
        billing_code=billing_code.strip() if billing_code else None,
        pi_contact=pi_contact,
    )


def access_level(user_id: int) -> sql.ColumnElement[AccessLevel]:
    is_admin = sa.select(1).where(User.id == user_id, User.is_admin)
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)

    has_write_access = sa.and_(
        SeqRequest.status == SeqRequestStatus.DRAFT,
        sa.or_(
            SeqRequest.requestor_id == user_id,
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == SeqRequest.group_id)
            ).correlate_except(links.UserAffiliation).exists()
        )
    )

    has_read_access = sa.or_(
        SeqRequest.requestor_id == user_id,
        sa.select(1).where(
            (links.UserAffiliation.user_id == user_id) &
            (links.UserAffiliation.group_id == SeqRequest.group_id)
        ).correlate_except(links.UserAffiliation).exists()
    )

    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (has_write_access, AccessLevel.WRITE),
        (has_read_access, AccessLevel.READ),
        else_=AccessLevel.NONE
    )


def search(
    name: str | None = None,
    requestor_name: str | None = None,
    group_name: str | None = None,
    name_weight: float = 0.5,
    requestor_name_weight: float = 0.25,
    group_name_weight: float = 0.25,
    statement: sql.Select[SeqRequest] = sa.select(SeqRequest),
) -> sql.Select[SeqRequest]:
    filter_conditions: list[sql.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if name is not None:
        filter_conditions.append(utils.safe_trgm_search(SeqRequest.name, name))
        relevance += sa.func.similarity(SeqRequest.name, name) * name_weight

    if requestor_name is not None:
        full_name = User.name.expression
        filter_conditions.append(utils.safe_trgm_search(full_name, requestor_name))
        relevance += sa.func.similarity(full_name, requestor_name) * requestor_name_weight

    if group_name is not None:
        filter_conditions.append(utils.safe_trgm_search(Group.name, group_name))
        relevance += sa.func.similarity(Group.name, group_name) * group_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if requestor_name is not None:
        statement = statement.join(User, SeqRequest.requestor_id == User.id)
    if group_name is not None:
        statement = statement.join(Group, SeqRequest.group_id == Group.id)

    return statement.order_by(sa.nulls_last(relevance.desc()))


def select(
    id: int | None = None,
    name: str | None = None,
    status: SeqRequestStatus | None = None,
    status_in: list[SeqRequestStatus] | None = None,
    submission_type: SubmissionType | None = None,
    submission_type_in: list[SubmissionType] | None = None,
    library_types_in: list[LibraryType] | None = None,
    show_drafts: bool = True,
    requestor_id: int | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    group_id: int | None = None,
    viewer_id: int | None = None,
    statement: sql.Select[SeqRequest] = sa.select(SeqRequest),
) -> sql.Select[SeqRequest]:
    return statement.where(*where_clauses(
        id=id,
        status=status,
        name=name,
        status_in=status_in,
        submission_type=submission_type,
        submission_type_in=submission_type_in,
        library_types_in=library_types_in,
        show_drafts=show_drafts,
        requestor_id=requestor_id,
        project_id=project_id,
        experiment_id=experiment_id,
        group_id=group_id,
        viewer_id=viewer_id,
    ))

def permissions(seq_request_id: int, user_id: int) -> sql.Select[AccessLevel]:
    return sa.select(access_level(user_id)).where(SeqRequest.id == seq_request_id)


def can_delete(user_id: int) -> sql.ColumnElement[bool]:
    """Insiders, or while DRAFT the requestor and the OWNER/MANAGER of the request's group.

    Plain group members may edit a group's draft (WRITE) but not delete another member's request."""
    is_insider = sa.select(1).where(User.id == user_id, User.is_insider)
    is_group_manager = sa.select(1).where(
        (links.UserAffiliation.user_id == user_id) &
        (links.UserAffiliation.group_id == SeqRequest.group_id) &
        links.UserAffiliation.affiliation_type.in_([AffiliationType.OWNER, AffiliationType.MANAGER])
    ).correlate_except(links.UserAffiliation).exists()
    return sa.or_(
        sa.exists(is_insider),
        sa.and_(
            SeqRequest.status == SeqRequestStatus.DRAFT,
            sa.or_(SeqRequest.requestor_id == user_id, is_group_manager),
        ),
    )


def delete_permission(seq_request_id: int, user_id: int) -> sql.Select[bool]:
    return sa.select(can_delete(user_id)).where(SeqRequest.id == seq_request_id)


def submitted_by(seq_request_id: int) -> sql.Select[tuple[User]]:
    """The user who last submitted the request (latest recorded `request.submit` run).

    Not the requestor: insiders may submit on a customer's behalf. Requests submitted before
    status tracking, or by the system, have no submitter."""
    return sa.select(User).join(OperationRun, OperationRun.actor_id == User.id).where(
        OperationRun.operation == "request.submit",
        OperationRun.subject_type == "seq_request",
        OperationRun.subject_id == seq_request_id,
    ).order_by(OperationRun.timestamp_utc.desc(), OperationRun.id.desc()).limit(1)


def where_clauses(
    id: int | None = None,
    name: str | None = None,
    status: SeqRequestStatus | None = None,
    status_in: list[SeqRequestStatus] | None = None,
    submission_type: SubmissionType | None = None,
    submission_type_in: list[SubmissionType] | None = None,
    library_types_in: list[LibraryType] | None = None,
    show_drafts: bool = True,
    requestor_id: int | None = None,
    project_id: int | None = None,
    experiment_id: int | None = None,
    group_id: int | None = None,
    viewer_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering seq requests.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(SeqRequest.id == id)
    if name is not None:
        clauses.append(SeqRequest.name == name)
    if status is not None:
        clauses.append(SeqRequest.status == status)
    if submission_type is not None:
        clauses.append(SeqRequest.submission_type == submission_type)
    if requestor_id is not None:
        clauses.append(
            sa.or_(
                SeqRequest.requestor_id == requestor_id,
                sa.select(1).where(
                    (links.UserAffiliation.user_id == requestor_id) &
                    (links.UserAffiliation.group_id == SeqRequest.group_id)
                ).correlate_except(links.UserAffiliation).exists(),
            )
        )
    if status_in is not None:
        clauses.append(SeqRequest.status.in_(status_in))
    if submission_type_in is not None:
        clauses.append(SeqRequest.submission_type.in_(submission_type_in))
    if library_types_in is not None:
        clauses.append(
            sa.select(1).where(
                (Library.seq_request_id == SeqRequest.id) &
                (Library.type.in_(library_types_in))  # type: ignore
            ).correlate_except(Library).exists()
        )
    if not show_drafts:
        clauses.append(
            sa.or_(
                SeqRequest.status != SeqRequestStatus.DRAFT,
                SeqRequest.requestor_id == requestor_id
            )
        )
    if group_id is not None:
        clauses.append(SeqRequest.group_id == group_id)
    if project_id is not None:
        clauses.append(
            sa.select(1).where(
                (Sample.project_id == project_id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == SeqRequest.id)
            ).correlate_except(Sample, links.SampleLibraryLink, Library).exists()
        )
    if experiment_id is not None:
        clauses.append(
            sa.select(1).where(
                (Library.experiment_id == experiment_id) &
                (Library.seq_request_id == SeqRequest.id)
            ).correlate_except(Library).exists()
        )
    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses
