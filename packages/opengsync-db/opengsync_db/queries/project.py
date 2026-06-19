import sqlalchemy as sa
from sqlalchemy import sql

from ..models import Project, User, Sample, Library, links
from ..categories import ProjectStatus, LibraryType, UserRole, AccessLevel
from ..core import utils


def create(
    title: str,
    description: str | None,
    owner_id: int,
    identifier: str | None = None,
    group_id: int | None = None,
    status: ProjectStatus = ProjectStatus.DRAFT,
) -> Project:
    return Project(
        identifier=identifier,
        title=title.strip(),
        description=(description.strip() or None) if description is not None else None,
        owner_id=owner_id,
        group_id=group_id,
        status_id=status.id,
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
        Project.status_id == ProjectStatus.DRAFT.id,
        sa.or_(
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == Project.group_id)
            ).correlate_except(links.UserAffiliation).exists(),
            Project.owner_id == user_id,
        )
    )

    has_read_access = sa.or_(
        Project.status_id != ProjectStatus.DRAFT.id,
        sa.or_(
            sa.select(1).where(
                (links.UserAffiliation.user_id == user_id) &
                (links.UserAffiliation.group_id == Project.group_id)
            ).correlate_except(links.UserAffiliation).exists(),
            Project.owner_id == user_id,
        )
    )
    
    return sa.case(
        (sa.exists(is_admin), AccessLevel.ADMIN),
        (sa.exists(is_insider), AccessLevel.INSIDER),
        (has_write_access, AccessLevel.WRITE),
        (has_read_access, AccessLevel.READ),
        else_=AccessLevel.NONE
    )



def search(
    title: str | None = None,
    identifier: str | None = None,
    owner_name: str | None = None,
    title_weight: float = 0.3,
    identifier_weight: float = 0.5,
    owner_name_weight: float = 0.2,
    statement: sql.Select[tuple[Project]] = sa.select(Project),
) -> sql.Select[tuple[Project]]:
    
    filter_conditions: list[sql.ColumnElement[bool]] = []
    relevance = sa.literal(0.0)

    if title:
        filter_conditions.append(utils.safe_trgm_search(Project.title, title))
        relevance += sa.func.similarity(Project.title, title) * title_weight

    if identifier:
        filter_conditions.append(utils.safe_ilike(Project.identifier, identifier))
        relevance += sa.func.similarity(Project.identifier, identifier) * identifier_weight

    if owner_name:
        filter_conditions.append(utils.safe_trgm_search(User.name.expression, owner_name))
        relevance += sa.func.similarity(User.name.expression, owner_name) * owner_name_weight

    if not filter_conditions:
        return statement

    statement = statement.where(sa.or_(*filter_conditions))

    if owner_name is not None:
        statement = statement.join(User, Project.owner_id == User.id)

    return statement.order_by(sa.nulls_last(relevance.desc()))


def select(
    id: int | None = None,
    identifier: str | None = None,
    title: str | None = None,
    owner_id: int | None = None,
    group_id: int | None = None,
    viewer_id: int | None = None,
    status: ProjectStatus | None = None,
    status_in: list[ProjectStatus] | None = None,
    seq_request_id: int | None = None,
    experiment_id: int | None = None,
    library_types_in: list[LibraryType] | None = None,
    user_id: int | None = None,
    statement: sql.Select[tuple[Project]] = sa.select(Project),
) -> sql.Select[tuple[Project]]:
    return statement.where(*where_clauses(
        id=id,
        identifier=identifier,
        title=title,
        owner_id=owner_id,
        group_id=group_id,
        viewer_id=viewer_id,
        status=status,
        status_in=status_in,
        seq_request_id=seq_request_id,
        experiment_id=experiment_id,
        library_types_in=library_types_in,
        user_id=user_id,
    ))
    
def permissions(project_id: int, user_id: int) -> sa.Select[tuple[AccessLevel]]:
    return sa.select(access_level(user_id)).where(Project.id == project_id)


def where_clauses(
    id: int | None = None,
    identifier: str | None = None,
    title: str | None = None,
    owner_id: int | None = None,
    group_id: int | None = None,
    viewer_id: int | None = None,
    status: ProjectStatus | None = None,
    status_in: list[ProjectStatus] | None = None,
    seq_request_id: int | None = None,
    experiment_id: int | None = None,
    library_types_in: list[LibraryType] | None = None,
    user_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering projects.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(Project.id == id)
    if identifier is not None:
        clauses.append(Project.identifier == identifier)
    if title is not None:
        clauses.append(Project.title == title)
    if owner_id is not None:
        clauses.append(Project.owner_id == owner_id)
    if group_id is not None:
        clauses.append(Project.group_id == group_id)
    if status is not None:
        clauses.append(Project.status_id == status.id)
    if status_in is not None:
        clauses.append(Project.status_id.in_([s.id for s in status_in]))
    if user_id is not None:
        clauses.append(
            sa.or_(
                Project.owner_id == user_id,
                sa.select(1).where(
                    (links.UserAffiliation.user_id == user_id) &
                    (links.UserAffiliation.group_id == Project.group_id)
                ).correlate_except(links.UserAffiliation).exists(),
                sa.select(1).where(
                    (links.ProjectAssigneeLink.user_id == user_id) &
                    (links.ProjectAssigneeLink.project_id == Project.id)
                ).correlate_except(links.ProjectAssigneeLink).exists(),
            )
        )
    if seq_request_id is not None:
        clauses.append(
            sa.select(1).where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.seq_request_id == seq_request_id)
            ).correlate_except(Sample, links.SampleLibraryLink, Library).exists()
        )
    if experiment_id is not None:
        clauses.append(
            sa.select(1).where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.experiment_id == experiment_id)
            ).correlate_except(Sample, links.SampleLibraryLink, Library).exists()
        )
    if library_types_in is not None:
        clauses.append(
            sa.select(1).where(
                (Sample.project_id == Project.id) &
                (links.SampleLibraryLink.sample_id == Sample.id) &
                (Library.id == links.SampleLibraryLink.library_id) &
                (Library.type_id.in_([lt.id for lt in library_types_in]))
            ).correlate_except(Sample, links.SampleLibraryLink, Library).exists()
        )
    if viewer_id is not None:
        clauses.append(access_level(viewer_id) >= AccessLevel.READ)

    return clauses
    