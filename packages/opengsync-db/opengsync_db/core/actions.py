import string
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal, Sequence
import sqlalchemy as sa
from sqlalchemy.orm import Session

from .. import models, exceptions, categories as C, queries as Q, to_utc
from ..transitions import run_operation, request as request_ops, create as create_ops, lab as lab_ops, release as release_ops

def link_sample_library(
    session: Session, sample_id: int, library_id: int,
    mux: Optional[dict] = None,
    flush: bool = True
) -> models.links.SampleLibraryLink:
    if session.query(models.links.SampleLibraryLink).where(
        models.links.SampleLibraryLink.sample_id == sample_id,
        models.links.SampleLibraryLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Sample with id {sample_id} and Library with id {library_id} are already linked")
    
    link = models.links.SampleLibraryLink(
        sample_id=sample_id,
        library_id=library_id,
        mux=mux,
    )

    session.add(link)

    if flush:
        session.flush()

    return link
    
def add_pool_to_lane(
    session: Session, experiment: models.Experiment, pool: models.Pool, lane: models.Lane, flush: bool = True
) -> models.Lane:
    if experiment.workflow.combined_lanes:
        num_m_reads_per_lane = pool.num_m_reads_requested / experiment.num_lanes if pool.num_m_reads_requested else None
    else:
        num_m_reads_per_lane = pool.num_m_reads_requested / (len(pool.lane_links) + 1) if pool.num_m_reads_requested else None

    for link in pool.lane_links:
        link.num_m_reads = num_m_reads_per_lane

    experiment.laned_pool_links.append(models.links.LanePoolLink(lane=lane, pool=pool, lane_num=lane.number, num_m_reads=num_m_reads_per_lane))
    
    session.add(experiment)

    if flush:
        session.flush()

    return lane
    
def remove_pool_from_lane(session: Session, experiment: models.Experiment, pool: models.Pool, lane: models.Lane, flush: bool = True) -> models.Lane:
    if (link := session.query(models.links.LanePoolLink).where(
        models.links.LanePoolLink.pool_id == pool.id,
        models.links.LanePoolLink.lane_id == lane.id,
    ).first()) is None:
        raise exceptions.LinkDoesNotExist(f"Lane with id '{lane.id}' and Pool with id '{pool.id}' are not linked.")
    
    experiment.laned_pool_links.remove(link)
    
    for _link in pool.lane_links:
        if _link.lane_id == lane.id:
            continue
        _link.num_m_reads = pool.num_m_reads_requested / len(pool.lane_links) if pool.num_m_reads_requested else None

    session.add(lane)
    session.add(pool)
    session.add(experiment)

    if flush:
        session.flush()
    return lane

def unlink_pool_experiment(session: Session, experiment_id: int, pool_id: int, flush: bool = True):
    if (experiment := session.get(models.Experiment, experiment_id)) is None:
        raise exceptions.NotFoundException(f"Experiment with id {experiment_id} does not exist")

    if (pool := session.get(models.Pool, pool_id)) is None:
        raise exceptions.NotFoundException(f"Pool with id {pool_id} does not exist")
    if pool.experiment_id != experiment_id:
        raise exceptions.LinkDoesNotExist(f"Pool with id {pool_id} is not linked to experiment with id {experiment_id}")
    
    for lane in experiment.lanes:
        if (link := session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool_id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first()) is not None:
            session.delete(link)

    for library in pool.libraries:
        library.experiment_id = None

    experiment.pools.remove(pool)
    session.add(pool)
    session.add(experiment)

    if flush:
        session.flush()

def unlink_sample_library(session: Session, sample_id: int, library_id: int, flush: bool = True):
    if (link := session.query(models.links.SampleLibraryLink).where(
        models.links.SampleLibraryLink.sample_id == sample_id,
        models.links.SampleLibraryLink.library_id == library_id,
    ).first()) is None:
        raise exceptions.LinkDoesNotExist(f"Sample with id {sample_id} and Library with id {library_id} are not linked")

    session.delete(link)

    if flush:
        session.flush()

def clone_library(
    session: Session, library_id: int, seq_request_id: int, indexed: bool, status: C.LibraryStatus
) -> models.Library:

    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.NotFoundException(f"Library with id {library_id} does not exist")

    original_library_id = library.original_library_id if library.original_library_id is not None else library.id
    # Clones are numbered across the original's lineage: existing clones of the original + 1
    clone_number = session.scalar(
        sa.select(sa.func.count()).select_from(models.Library).where(models.Library.original_library_id == original_library_id)
    ) + 1

    cloned_library = Q.library.create(
        name=library.name,
        sample_name=library.sample_name,
        library_type=library.type,
        seq_request_id=seq_request_id,
        owner_id=library.owner_id,
        genome_ref=library.genome_ref,
        service_type=library.service_type,
        mux_type=library.mux_type,
        properties=library.properties,
        index_type=library.index_type,
        nuclei_isolation=library.nuclei_isolation,
        clone_number=clone_number,
        original_library_id=original_library_id,
        status=status
    )
    # The links below need the clone's id
    session.add(cloned_library)
    session.flush()

    for sample_link in library.sample_links:
        link_sample_library(
            session=session,
            sample_id=sample_link.sample_id,
            library_id=cloned_library.id,
            mux=sample_link.mux if sample_link.mux is not None else None,
        )

    for feature in library.features:
        link_feature_library(
            session=session,
            feature_id=feature.id,
            library_id=cloned_library.id
        )

    if indexed:
        for index in library.indices:
            add_index_to_library(
                session=session,
                library_id=cloned_library.id,
                index_kit_i7_id=index.index_kit_i7_id,
                name_i7=index.name_i7,
                sequence_i7=index.sequence_i7,
                index_kit_i5_id=index.index_kit_i5_id,
                name_i5=index.name_i5,
                sequence_i5=index.sequence_i5,
                orientation=index.orientation,
            )

    return cloned_library


def add_index_to_library(
    session: Session, library_id: int,
    index_kit_i7_id: Optional[int], name_i7: Optional[str], sequence_i7: Optional[str],
    index_kit_i5_id: Optional[int], name_i5: Optional[str], sequence_i5: Optional[str],
    orientation: Optional[C.BarcodeOrientation],
    flush: bool = True
) -> models.Library:

    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.NotFoundException(f"Library with id {library_id} does not exist")
    
    if index_kit_i7_id is not None:
        if session.get(models.IndexKit, index_kit_i7_id) is None:
            raise exceptions.NotFoundException(f"Index kit with id {index_kit_i7_id} does not exist")
        
    if index_kit_i5_id is not None:
        if session.get(models.IndexKit, index_kit_i5_id) is None:
            raise exceptions.NotFoundException(f"Index kit with id {index_kit_i5_id} does not exist")

    library.indices.append(models.LibraryIndex(
        library_id=library_id,
        name_i7=name_i7,
        sequence_i7=sequence_i7,
        name_i5=name_i5,
        sequence_i5=sequence_i5,
        index_kit_i7_id=index_kit_i7_id,
        index_kit_i5_id=index_kit_i5_id,
        orientation=orientation,
    ))

    session.add(library)

    if flush:
        session.flush()

    return library

def link_feature_library(session: Session, feature_id: int, library_id: int):
    if (feature := session.get(models.Feature, feature_id)) is None:
        raise exceptions.NotFoundException(f"Feature with id {feature_id} does not exist")
    
    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.NotFoundException(f"Library with id {library_id} does not exist")
    
    if session.query(models.links.LibraryFeatureLink).where(
        models.links.LibraryFeatureLink.feature_id == feature_id,
        models.links.LibraryFeatureLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Feature with id {feature_id} and Library with id {library_id} are already linked")
    
    library.features.append(feature)
    session.add(library)


_PROCESS_OPERATIONS = {
    C.SeqRequestStatus.ACCEPTED: request_ops.ACCEPT,
    C.SeqRequestStatus.DRAFT: request_ops.RETURN,
    C.SeqRequestStatus.REJECTED: request_ops.REJECT,
}


def process_seq_request(session: Session, seq_request: models.SeqRequest, status: C.SeqRequestStatus) -> models.SeqRequest:
    if (operation := _PROCESS_OPERATIONS.get(status)) is None:
        raise TypeError(f"Cannot process request to '{status}'.")
    with run_operation(session, operation, subject=seq_request):
        return _process_seq_request(session, seq_request, status)


def _process_seq_request(session: Session, seq_request: models.SeqRequest, status: C.SeqRequestStatus) -> models.SeqRequest:
    seq_request.status = status

    if seq_request.status in [C.SeqRequestStatus.DRAFT, C.SeqRequestStatus.REJECTED]:
        seq_request.timestamp_submitted_utc = None
        if seq_request.sample_submission_event is not None:
            session.delete(seq_request.sample_submission_event)
            seq_request.sample_submission_event = None
    
    if status == C.SeqRequestStatus.ACCEPTED:
        library_status = C.LibraryStatus.ACCEPTED
        pool_status = C.PoolStatus.ACCEPTED
    elif status == C.SeqRequestStatus.DRAFT:
        library_status = C.LibraryStatus.DRAFT
        pool_status = C.PoolStatus.DRAFT
    elif status == C.SeqRequestStatus.REJECTED:
        library_status = C.LibraryStatus.REJECTED
        pool_status = C.PoolStatus.REJECTED
    else:
        raise TypeError(f"Cannot process request to '{status}'.")

    for sample in seq_request.samples:
        if sample.status != C.SampleStatus.DRAFT:
            continue  # Sample was not prepared in-house -> no specimen stored
        if status == C.SeqRequestStatus.ACCEPTED:
            sample.status = C.SampleStatus.WAITING_DELIVERY
        elif status == C.SeqRequestStatus.DRAFT:
            sample.status = C.SampleStatus.DRAFT
        # On request rejection, samples stay draft so that they can be re-submitted
    
    is_prepared = status == C.SeqRequestStatus.ACCEPTED
    for library in seq_request.libraries:
        if library.status == C.LibraryStatus.SUBMITTED:
            library.status = library_status
        if library_status != C.LibraryStatus.ACCEPTED:
            continue
        
        if library.pool_id is not None:
            library.status = C.LibraryStatus.POOLED

        is_prepared = is_prepared and library.status.id >= C.LibraryStatus.POOLED.id
    
    if status == C.SeqRequestStatus.ACCEPTED:
        seq_request.status = C.SeqRequestStatus.ACCEPTED

    for pool in seq_request.pools:
        if pool.status != C.PoolStatus.SUBMITTED:
            continue
        pool.status = pool_status

    if status == C.SeqRequestStatus.ACCEPTED:
        for project in seq_request.projects:
            project.status = C.ProjectStatus.PROCESSING
            session.add(project)

    session.add(seq_request)
    return seq_request

def clone_pool(session: Session, pool_id: int, status: C.PoolStatus, seq_request_id: int | None = None) -> models.Pool:

    if (pool := session.get(models.Pool, pool_id)) is None:
        raise exceptions.NotFoundException(f"Pool with id {pool_id} does not exist")

    original_pool_id = pool.original_pool_id if pool.original_pool_id is not None else pool.id
    # Clones are numbered across the original's lineage: existing clones of the original + 1
    clone_number = session.scalar(
        sa.select(sa.func.count()).select_from(models.Pool).where(models.Pool.original_pool_id == original_pool_id)
    ) + 1

    cloned_pool = Q.pool.create(
        name=pool.name,
        owner_id=pool.owner_id,
        seq_request_id=seq_request_id or pool.seq_request_id,
        num_m_reads_requested=pool.num_m_reads_requested,
        lab_prep_id=pool.lab_prep_id,
        contact_email=pool.contact.email if pool.contact.email is not None else "unknown",
        contact_name=pool.contact.name,
        contact_phone=pool.contact.phone,
        pool_type=pool.type,
        original_pool_id=original_pool_id,
        status=status,
        clone_number=clone_number,
    )

    cloned_pool.avg_fragment_size = pool.avg_fragment_size
    cloned_pool.qubit_concentration = pool.qubit_concentration
    cloned_pool.num_m_reads_requested = pool.num_m_reads_requested

    cloned_pool.ba_report_id = pool.ba_report_id
    # Callers link libraries to the clone by id
    session.add(cloned_pool)
    session.flush()

    return cloned_pool

def merge_pool(session: Session, merged_pool_id: int, pool_ids: Sequence[int], flush: bool = True) -> models.Pool:
    if merged_pool_id in pool_ids:
        raise exceptions.InvalidOperation("Cannot merge a pool into itself")

    if (merged_pool := session.get(models.Pool, merged_pool_id)) is None:
        raise exceptions.NotFoundException(f"New Pool with id {merged_pool} does not exist")

    from sqlalchemy import orm
    pools = session.query(models.Pool).filter(
        models.Pool.id.in_(pool_ids)
    ).options(orm.joinedload(models.Pool.libraries)).all()

    if len(pool_ids) != len(pools):
        raise exceptions.NotFoundException("One or more pools to merge do not exist")

    for pool in pools:
        for library in pool.libraries:
            library.pool_id = merged_pool.id

        pool.status = C.PoolStatus.REPOOLED
        pool.merged_to_pool_id = merged_pool.id
        session.add(pool)

    session.add(merged_pool)

    if flush:
        session.flush()
    return merged_pool


def add_libraries_to_prep(session: Session, lab_prep: models.LabPrep, libraries: Sequence[models.Library]) -> models.LabPrep:
    """Adds libraries to a lab prep; libraries below PREPARING become PREPARING (as legacy LabPrepBP.add_library)."""
    with run_operation(session, lab_ops.ADD_LIBRARIES, subject=lab_prep):
        for library in libraries:
            if library.status < C.LibraryStatus.PREPARING:
                library.status = C.LibraryStatus.PREPARING
            lab_prep.libraries.append(library)
        session.add(lab_prep)
    return lab_prep


def remove_library_from_prep(
    session: Session, lab_prep_id: int, library_id: int, flush: bool = True
) -> models.LabPrep:
    """Removes a library from a lab prep; a PREPARING library goes back to ACCEPTED (as legacy LabPrepBP.remove_library)."""
    if (lab_prep := session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.NotFoundException(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.NotFoundException(f"Library with id '{library_id}', not found.")
    
    with run_operation(session, lab_ops.REMOVE_LIBRARY, subject=lab_prep):
        if library.status == C.LibraryStatus.PREPARING:
            library.status = C.LibraryStatus.ACCEPTED
        
        lab_prep.libraries.remove(library)
        session.add(lab_prep)
        if flush:
            session.flush()
    return lab_prep

def set_library_seq_quality(
    session: Session, library: models.Library | None,
    experiment: models.Experiment,
    lane: int,
    num_reads: int,
    qc: dict | None = None,
) -> models.SeqQuality:
    if library is not None:
        if library.status < C.LibraryStatus.SEQUENCED:
            library.status = C.LibraryStatus.SEQUENCED
        if library.pool is not None:
            if library.pool.status < C.PoolStatus.SEQUENCED:
                library.pool.status = C.PoolStatus.SEQUENCED
        
        session.add(library)
        
    if (quality := session.query(models.SeqQuality).where(
        (models.SeqQuality.library_id == library.id) if library is not None else (models.SeqQuality.library_id.is_(None)),
        models.SeqQuality.experiment_id == experiment.id,
        models.SeqQuality.lane == lane,
    ).first()) is not None:
        quality.num_reads = num_reads
        quality.qc = qc
    else:
        quality = models.SeqQuality(
            library_id=library.id if library is not None else None,
            lane=lane, experiment_id=experiment.id,
            num_reads=num_reads, qc=qc
        )

    session.add(quality)

    return quality

def remove_all_barcodes_from_kit(
    session: Session, index_kit: models.IndexKit, flush: bool = True
) -> models.IndexKit:
    # Bulk delete: a barcode is reachable through both Adapter.barcodes_i7 and Adapter.barcodes_i5,
    # so deleting through the ORM issued its DELETE twice (SAWarning: 0 rows matched).
    session.execute(sa.delete(models.Barcode).where(models.Barcode.index_kit_id == index_kit.id))
    session.execute(sa.delete(models.Adapter).where(models.Adapter.index_kit_id == index_kit.id))
    session.expire(index_kit, ["adapters", "barcodes"])

    if flush:
        session.flush()
    return index_kit


def add_library_to_plate(
    session: Session, plate: models.Plate, library: models.Library, well_idx: int
) -> models.Plate:
    plate.sample_links.append(models.links.SamplePlateLink(
        plate=plate, well_idx=well_idx, library=library
    ))
    session.add(plate)
    return plate

def link_pool_experiment(session: Session, experiment: models.Experiment, pool: models.Pool, flush: bool = True):
    if pool.experiment_id is not None:
        raise exceptions.LinkAlreadyExists(f"Pool with id {pool.id} is already linked to an experiment")

    experiment.pools.append(pool)

    for library in pool.libraries:
        library.experiment_id = experiment.id

    if experiment.workflow.combined_lanes:
        for lane in experiment.lanes:
            add_pool_to_lane(session=session, experiment=experiment, pool=pool, lane=lane)

    session.add(experiment)
    session.add(pool)
    
    if flush:
        session.flush()


def dilute_pool(
    session: Session,
    pool: models.Pool,
    qubit_concentration: float,
    operator_id: int,
    volume_ul: float | None = None,
    flush: bool = True
) -> models.Pool:
    n = len(pool.dilutions)

    def to_identifier(n: int) -> str:
        out = ""

        while n >= 0:
            n, r = divmod(n, 26)
            out = string.ascii_uppercase[r] + out
            n -= 1

        return out

    dilution = models.PoolDilution(
        pool_id=pool.id,
        operator_id=operator_id,
        identifier=to_identifier(n),
        qubit_concentration=qubit_concentration,
        volume_ul=volume_ul,
    )

    pool.dilutions.append(dilution)
    session.add(pool)
    session.refresh(pool)
    
    if flush:
        session.flush()

    return pool

def merge_pools(session: Session, merged_pool: models.Pool, pools: Sequence[models.Pool], flush: bool = True) -> models.Pool:
    for pool in pools:
        for library in pool.libraries:
            library.pool_id = merged_pool.id

        pool.status = C.PoolStatus.REPOOLED
        pool.merged_to_pool_id = merged_pool.id
        session.add(pool)

    session.add(merged_pool)

    if flush:
        session.flush()
    return merged_pool

def merge_projects(session: Session, project_dst: models.Project, project_src: models.Project) -> models.Project:
    with run_operation(session, release_ops.MERGE, subject=project_dst):
        return _merge_projects(session, project_dst, project_src)


def _merge_projects(session: Session, project_dst: models.Project, project_src: models.Project) -> models.Project:
    dst_sample_mapping = {sample.name: sample for sample in project_dst.samples}

    samples_to_delete = []

    for sample in project_src.samples:
        if sample.name in dst_sample_mapping:
            dst_sample = dst_sample_mapping[sample.name]
            for attr in sample.attributes:
                if (dst_attr := dst_sample.get_attribute(attr.name)) is None:
                    dst_sample.set_attribute(attr.name, attr.value, type=attr.type)
                elif dst_attr.type_id != attr.type_id:
                    raise ValueError(f"Sample attribute conflict for sample '{sample.name}' on attribute '{attr}' with value '{attr.value}' (destination type: '{dst_attr.type}')")
                elif dst_attr.value != attr.value:
                    raise ValueError(f"Sample attribute conflict for sample '{sample.name}' on attribute '{attr}' with value '{attr.value}' (destination value: '{dst_attr.value}')")

            # Re-parent through the relationship so the link leaves the source
            # sample's delete-orphan collection before the source is deleted.
            dst_library_ids = {link.library_id for link in dst_sample.library_links}
            for link in list(sample.library_links):
                if link.library_id in dst_library_ids:
                    session.delete(link)
                else:
                    link.sample = dst_sample
                    dst_library_ids.add(link.library_id)
                    session.add(link)

            dst_sample.qubit_concentration = dst_sample.qubit_concentration or sample.qubit_concentration
            dst_sample.avg_fragment_size = dst_sample.avg_fragment_size or sample.avg_fragment_size
            dst_sample.timestamp_stored_utc = dst_sample.timestamp_stored_utc or sample.timestamp_stored_utc
            if dst_sample.status is None or (sample.status is not None and dst_sample.status < sample.status):
                dst_sample.status = sample.status
            dst_sample.ba_report_id = dst_sample.ba_report_id or sample.ba_report_id
            session.add(dst_sample)

            samples_to_delete.append(sample)
        else:
            sample.project_id = project_dst.id
            session.add(sample)

    for sample in samples_to_delete:
        session.delete(sample)

    dst_assignee_ids = {u.id for u in project_dst.assignees}
    for user in project_src.assignees:
        if user.id not in dst_assignee_ids:
            project_dst.assignees.append(user)

    for data_path in list(project_src.data_paths):
        data_path.project = project_dst
        session.add(data_path)

    session.add(project_dst)
    session.flush()
    # Reload the source's collections, otherwise the delete would detach the moved samples.
    # Only the destination project remains; the source's assignee links are removed with it.
    session.expire(project_src)
    session.delete(project_src)
    return project_dst


# Plain foreign keys to `lims_user.id` that `merge_users` re-points to the destination user.
# Assignee links, affiliations and passkeys need extra handling and are merged separately.
USER_REFERENCES: dict[str, sa.orm.InstrumentedAttribute] = {
    "Projects": models.Project.owner_id,
    "Sequencing requests": models.SeqRequest.requestor_id,
    "Samples": models.Sample.owner_id,
    "Libraries": models.Library.owner_id,
    "Pools": models.Pool.owner_id,
    "Plates": models.Plate.owner_id,
    "Lab preps": models.LabPrep.creator_id,
    "Experiments (operator)": models.Experiment.operator_id,
    "Pool dilutions": models.PoolDilution.operator_id,
    "Media files": models.MediaFile.uploader_id,
    "Comments": models.Comment.author_id,
    "TODO comments": models.TODOComment.author_id,
    "Events": models.Event.creator_id,
    "API tokens": models.APIToken.owner_id,
    "Share tokens": models.ShareToken.owner_id,
    "Status history entries": models.OperationRun.actor_id,
    "Checklist log entries": models.ChecklistLog.actor_id,
}

_USER_ASSIGNEE_LINKS = (
    ("Project assignments", models.links.ProjectAssigneeLink, models.links.ProjectAssigneeLink.project_id),
    ("Sequencing request assignments", models.links.SeqRequestAssigneeLink, models.links.SeqRequestAssigneeLink.seq_request_id),
)


@dataclass
class UserMergePreview:
    counts: list[tuple[str, int]]
    """Rows referencing the source user that move to the destination (non-zero only)."""
    role: C.UserRole
    """Role the destination user ends up with."""
    affiliation_upgrades: list[tuple[str, C.AffiliationType]]
    """Shared groups where the destination user gets the source user's stronger affiliation."""
    num_passkeys: int
    passkeys_move: bool
    """True if the source passkeys move over, False if they are deleted with the source user."""
    conflicts: list[str]
    """Problems that block the merge."""


def _user_merge_conflicts(session: Session, user_dst: models.User, user_src: models.User) -> list[str]:
    if user_dst.id == user_src.id:
        return ["Source and destination users cannot be the same."]

    dst_titles = sa.select(models.Project.title).where(models.Project.owner_id == user_dst.id)
    clashing_titles = session.scalars(
        sa.select(models.Project.title)
        .where(models.Project.owner_id == user_src.id, models.Project.title.in_(dst_titles))
        .order_by(models.Project.title)
    ).all()
    if clashing_titles:
        return [
            "Both users own projects with the same title, merge or rename them first: "
            + ", ".join(f"'{title}'" for title in clashing_titles)
        ]
    return []


def _merged_role(user_dst: models.User, user_src: models.User) -> C.UserRole:
    return max(user_dst.role, user_src.role, key=lambda role: role.privilege_rank)


def _passkeys_move(user_dst: models.User, user_src: models.User, num_passkeys: int) -> bool:
    # A passkey only works with the WebAuthn user handle it was registered under,
    # so it can move only if the destination user has no handle of its own yet.
    return num_passkeys > 0 and user_dst.webauthn_user_handle is None and user_src.webauthn_user_handle is not None


def merge_users_preview(session: Session, user_dst: models.User, user_src: models.User) -> UserMergePreview:
    counts = []
    for label, column in USER_REFERENCES.items():
        if (count := session.scalar(sa.select(sa.func.count()).select_from(column.class_).where(column == user_src.id))):
            counts.append((label, count))
    for label, link, _ in _USER_ASSIGNEE_LINKS:
        if (count := session.scalar(sa.select(sa.func.count()).select_from(link).where(link.user_id == user_src.id))):
            counts.append((label, count))

    UA = models.links.UserAffiliation
    dst_types = {
        group_id: affiliation_type for group_id, affiliation_type
        in session.execute(sa.select(UA.group_id, UA.affiliation_type).where(UA.user_id == user_dst.id))
    }
    affiliation_upgrades = []
    num_groups = 0
    for affiliation in session.scalars(sa.select(UA).where(UA.user_id == user_src.id)):
        if (dst_type := dst_types.get(affiliation.group_id)) is None:
            num_groups += 1
        elif affiliation.affiliation_type < dst_type:
            affiliation_upgrades.append((affiliation.group.name, affiliation.affiliation_type))
    if num_groups:
        counts.append(("Group memberships", num_groups))

    num_passkeys = session.scalar(
        sa.select(sa.func.count()).select_from(models.UserPasskey).where(models.UserPasskey.user_id == user_src.id)
    ) or 0

    return UserMergePreview(
        counts=counts,
        role=_merged_role(user_dst, user_src),
        affiliation_upgrades=affiliation_upgrades,
        num_passkeys=num_passkeys,
        passkeys_move=_passkeys_move(user_dst, user_src, num_passkeys),
        conflicts=_user_merge_conflicts(session, user_dst, user_src),
    )


def merge_users(session: Session, user_dst: models.User, user_src: models.User) -> models.User:
    """Moves everything that references ``user_src`` to ``user_dst`` and deletes ``user_src``.

    ``user_dst`` keeps its email and password, gets the more privileged of both roles and,
    in groups both users belong to, the stronger affiliation. Raises ``ValueError`` before
    changing anything if the users cannot be merged.
    """
    if (conflicts := _user_merge_conflicts(session, user_dst, user_src)):
        raise ValueError(" ".join(conflicts))

    src_id, dst_id = user_src.id, user_dst.id

    num_passkeys = session.scalar(
        sa.select(sa.func.count()).select_from(models.UserPasskey).where(models.UserPasskey.user_id == src_id)
    ) or 0
    if _passkeys_move(user_dst, user_src, num_passkeys):
        handle = user_src.webauthn_user_handle
        user_src.webauthn_user_handle = None
        session.flush()  # free the unique handle before the destination takes it
        user_dst.webauthn_user_handle = handle
        session.execute(
            sa.update(models.UserPasskey).where(models.UserPasskey.user_id == src_id).values(user_id=dst_id),
            execution_options={"synchronize_session": False},
        )

    user_dst.role = _merged_role(user_dst, user_src)
    if user_src.last_login is not None and (user_dst.last_login is None or user_dst.last_login < user_src.last_login):
        user_dst.last_login = user_src.last_login

    # Shared groups: keep the stronger affiliation (OWNER has the lowest id) and drop the source row.
    UA = models.links.UserAffiliation
    dst_affiliations = {a.group_id: a for a in session.scalars(sa.select(UA).where(UA.user_id == dst_id))}
    for affiliation in session.scalars(sa.select(UA).where(UA.user_id == src_id)).all():
        if (dst_affiliation := dst_affiliations.get(affiliation.group_id)) is None:
            continue
        if affiliation.affiliation_type < dst_affiliation.affiliation_type:
            dst_affiliation.affiliation_type = affiliation.affiliation_type
        session.delete(affiliation)
    session.flush()

    sync = {"synchronize_session": False}
    session.execute(sa.update(UA).where(UA.user_id == src_id).values(user_id=dst_id), execution_options=sync)

    for _, link, other_id in _USER_ASSIGNEE_LINKS:
        session.execute(
            sa.delete(link).where(link.user_id == src_id, other_id.in_(sa.select(other_id).where(link.user_id == dst_id))),
            execution_options=sync,
        )
        session.execute(sa.update(link).where(link.user_id == src_id).values(user_id=dst_id), execution_options=sync)

    for column in USER_REFERENCES.values():
        session.execute(
            sa.update(column.class_).where(column == src_id).values({column.key: dst_id}),
            execution_options=sync,
        )

    # The bulk statements bypassed the identity map: reload before deleting the source user,
    # so its delete cascades see the now-empty collections.
    session.expire_all()
    if (src := session.get(models.User, src_id)) is not None:
        session.delete(src)
    session.flush()
    if (dst := session.get(models.User, dst_id)) is None:
        raise exceptions.NotFoundException(f"User with id {dst_id} does not exist")
    return dst


def split_project(
    session: Session,
    project_src: models.Project,
    project_dst: models.Project,
    sample_ids: Sequence[int],
    destination_status: C.ProjectStatus,
) -> models.Project:
    """Move selected samples from ``project_src`` into ``project_dst``.

    Samples with names that already exist in the destination are merged.  All
    conflicts are checked before any objects are changed so callers can safely
    turn a ``ValueError`` into a form validation response.
    """
    selected_ids = list(sample_ids)
    if not selected_ids:
        raise ValueError("At least one sample must be selected.")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("A sample may only be selected once.")
    if project_src.id == project_dst.id:
        raise ValueError("Source and destination projects cannot be the same.")

    source_samples = {sample.id: sample for sample in project_src.samples}
    missing_ids = set(selected_ids) - source_samples.keys()
    if missing_ids:
        missing = ", ".join(str(sample_id) for sample_id in sorted(missing_ids))
        raise ValueError(f"Selected samples do not belong to the source project: {missing}.")

    destination_by_name = {sample.name: sample for sample in project_dst.samples}

    # Preflight sample attributes before changing a project or a link.  A
    # duplicate link is intentionally kept on the destination sample; its
    # source counterpart is discarded below.
    for sample_id in selected_ids:
        source_sample = source_samples[sample_id]
        destination_sample = destination_by_name.get(source_sample.name)
        if destination_sample is None:
            continue

        destination_attributes = {attribute.name: attribute for attribute in destination_sample.attributes}
        for attribute in source_sample.attributes:
            destination_attribute = destination_attributes.get(attribute.name)
            if destination_attribute is None:
                continue
            if destination_attribute.type_id != attribute.type_id:
                raise ValueError(
                    f"Sample attribute conflict for sample '{source_sample.name}' on attribute "
                    f"'{attribute.name}': incompatible attribute types."
                )
            if destination_attribute.value != attribute.value:
                raise ValueError(
                    f"Sample attribute conflict for sample '{source_sample.name}' on attribute "
                    f"'{attribute.name}': incompatible attribute values."
                )

    for sample_id in selected_ids:
        source_sample = source_samples[sample_id]
        destination_sample = destination_by_name.get(source_sample.name)
        if destination_sample is None:
            source_sample.project_id = project_dst.id
            session.add(source_sample)
            continue

        destination_library_ids = {link.library_id for link in destination_sample.library_links}
        for link in list(source_sample.library_links):
            if link.library_id in destination_library_ids:
                session.delete(link)
            else:
                link.sample = destination_sample
                destination_library_ids.add(link.library_id)
                session.add(link)

        destination_plate_links = {
            (link.plate_id, link.well_idx): link
            for link in destination_sample.plate_links
        }
        for link in list(source_sample.plate_links):
            if (link.plate_id, link.well_idx) in destination_plate_links:
                session.delete(link)
            else:
                link.sample = destination_sample
                session.add(link)

        for attribute in source_sample.attributes:
            if destination_sample.get_attribute(attribute.name) is None:
                destination_sample.set_attribute(attribute.name, attribute.value, type=attribute.type)

        destination_sample.qubit_concentration = destination_sample.qubit_concentration or source_sample.qubit_concentration
        destination_sample.avg_fragment_size = destination_sample.avg_fragment_size or source_sample.avg_fragment_size
        destination_sample.timestamp_stored_utc = destination_sample.timestamp_stored_utc or source_sample.timestamp_stored_utc
        # SampleStatus IDs represent the progression order used when merging
        # duplicate samples, so retain the furthest progressed status.
        if destination_sample.status is None or (
            source_sample.status is not None and destination_sample.status < source_sample.status
        ):
            destination_sample.status = source_sample.status
        destination_sample.ba_report_id = destination_sample.ba_report_id or source_sample.ba_report_id
        session.add(destination_sample)
        session.delete(source_sample)

    project_dst.status = destination_status
    session.add(project_dst)
    session.flush()
    return project_dst

def submit_seq_request(session: Session, seq_request: models.SeqRequest) -> models.SeqRequest:
    with run_operation(session, request_ops.SUBMIT, subject=seq_request):
        return _submit_seq_request(session, seq_request)


def _submit_seq_request(session: Session, seq_request: models.SeqRequest) -> models.SeqRequest:
    seq_request.status = C.SeqRequestStatus.SUBMITTED
    seq_request.review_checklist = None
    seq_request.timestamp_submitted_utc = to_utc(datetime.now())
    
    for library in seq_request.libraries:
        if library.status != C.LibraryStatus.DRAFT:
            continue
        library.status = C.LibraryStatus.SUBMITTED

    for pool in seq_request.pools:
        if pool.status != C.PoolStatus.DRAFT:
            continue
        pool.status = C.PoolStatus.SUBMITTED
        session.add(pool)

    session.add(seq_request)
    return seq_request


def clone_seq_request(session: Session, seq_request: models.SeqRequest, method: Literal["pooled", "indexed", "raw"]) -> models.SeqRequest:
    with run_operation(session, create_ops.REQUEST_CLONE, subject=seq_request):
        return _clone_seq_request(session, seq_request, method)


def _clone_seq_request(session: Session, seq_request: models.SeqRequest, method: Literal["pooled", "indexed", "raw"]) -> models.SeqRequest:
    if method not in {"pooled", "indexed", "raw"}:
        raise ValueError(f"Method should be one of: {', '.join(['pooled', 'indexed', 'raw'])}")
    
    if method == "raw":
        submission_type = C.SubmissionType.RAW_SAMPLES
    elif method == "indexed":
        submission_type = C.SubmissionType.UNPOOLED_LIBRARIES
    elif method == "pooled":
        submission_type = C.SubmissionType.POOLED_LIBRARIES

    cloned_request = Q.seq_request.create(
        name=f"RE: {seq_request.name}"[:models.SeqRequest.name.type.length],
        requestor=seq_request.requestor,
        group=seq_request.group,
        description=seq_request.description,
        billing_contact=seq_request.billing_contact,
        data_delivery_mode=seq_request.data_delivery_mode,
        read_type=seq_request.read_type,
        submission_type=submission_type,
        contact_person=seq_request.contact_person,
        organization_contact=seq_request.organization_contact,
        bioinformatician_contact=seq_request.bioinformatician_contact,
        read_length=seq_request.read_length,
        num_lanes=seq_request.num_lanes,
        special_requirements=seq_request.special_requirements,
        billing_code=seq_request.billing_code,
    )
    # The cloned libraries and pools need the request's id
    session.add(cloned_request)
    session.flush()

    if method == "pooled":
        pools: dict[int, models.Pool] = {}
        for library in seq_request.libraries:
            cloned_library = clone_library(session=session, library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=C.LibraryStatus.POOLED)
            if library.pool_id is not None:
                if library.pool_id not in pools.keys():
                    pools[library.pool_id] = clone_pool(session=session, pool_id=library.pool_id, seq_request_id=cloned_request.id, status=C.PoolStatus.STORED)
                cloned_library.pool_id = pools[library.pool_id].id
    elif method == "indexed":
        for library in seq_request.libraries:
            clone_library(session=session, library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=C.LibraryStatus.STORED)
    elif method == "raw":
        for library in seq_request.libraries:
            clone_library(session=session, library_id=library.id, seq_request_id=cloned_request.id, indexed=False, status=C.LibraryStatus.ACCEPTED)

    session.add(cloned_request)
    return cloned_request


def release_project_data(
    session: Session,
    project: models.Project,
    seq_requests: Sequence[models.SeqRequest],
    recipients: Sequence[str],
    mark_project_delivered: bool | None,
) -> models.Project:
    """Statuses of a project data release, shared by the release API and the 'Share data' action.

    - project: DELIVERED if ``mark_project_delivered`` is true, or (``None``) automatically once every
      library of the requests is SEQUENCED or beyond; never moved back from a later status
    - delivery emails of the requests that received the data: DISPATCHED
    - libraries of the project: SEQUENCED → SHARED

    The caller runs it inside its operation (``api.release_project`` or ``project.share_data``).
    """
    if mark_project_delivered is None:
        mark_project_delivered = all(
            library.status >= C.LibraryStatus.SEQUENCED
            for seq_request in seq_requests
            for library in seq_request.libraries
        )
    if mark_project_delivered and project.status < C.ProjectStatus.DELIVERED:
        project.status = C.ProjectStatus.DELIVERED
        session.add(project)

    for seq_request in seq_requests:
        for link in seq_request.delivery_email_links:
            if link.email in recipients:
                link.status = C.DeliveryStatus.DISPATCHED
        session.add(seq_request)

    for library in project.libraries:
        if library.status == C.LibraryStatus.SEQUENCED:
            library.status = C.LibraryStatus.SHARED
            session.add(library)
    return project
