import string
from datetime import datetime
from typing import Optional, Literal, Sequence
from sqlalchemy.orm import Session

from .. import models, exceptions, categories as C, queries as Q, to_utc

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
        raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

    if (pool := session.get(models.Pool, pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
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
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")

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
        clone_number=library.clone_number + 1,
        original_library_id=library.original_library_id if library.original_library_id is not None else library.id,
        status=status
    )

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
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if index_kit_i7_id is not None:
        if session.get(models.IndexKit, index_kit_i7_id) is None:
            raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i7_id} does not exist")
        
    if index_kit_i5_id is not None:
        if session.get(models.IndexKit, index_kit_i5_id) is None:
            raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i5_id} does not exist")

    library.indices.append(models.LibraryIndex(
        library_id=library_id,
        name_i7=name_i7,
        sequence_i7=sequence_i7,
        name_i5=name_i5,
        sequence_i5=sequence_i5,
        index_kit_i7_id=index_kit_i7_id,
        index_kit_i5_id=index_kit_i5_id,
        _orientation=orientation.id if orientation is not None else None,
    ))

    session.add(library)

    if flush:
        session.flush()

    return library

def link_feature_library(session: Session, feature_id: int, library_id: int):
    if (feature := session.get(models.Feature, feature_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
    
    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
    
    if session.query(models.links.LibraryFeatureLink).where(
        models.links.LibraryFeatureLink.feature_id == feature_id,
        models.links.LibraryFeatureLink.library_id == library_id,
    ).first():
        raise exceptions.LinkAlreadyExists(f"Feature with id {feature_id} and Library with id {library_id} are already linked")
    
    library.features.append(feature)
    session.add(library)


def process_seq_request(session: Session, seq_request: models.SeqRequest, status: C.SeqRequestStatus) -> models.SeqRequest:
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
        elif status == C.SeqRequestStatus.REJECTED:
            sample.status = C.SampleStatus.REJECTED
    
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
        raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

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
        original_pool_id=pool.original_pool_id if pool.original_pool_id is not None else pool.id,
        status=status,
        clone_number=pool.clone_number + 1,
    )

    cloned_pool.avg_fragment_size = pool.avg_fragment_size
    cloned_pool.qubit_concentration = pool.qubit_concentration
    cloned_pool.num_m_reads_requested = pool.num_m_reads_requested

    cloned_pool.ba_report_id = pool.ba_report_id

    return cloned_pool

def merge_pool(session: Session, merged_pool_id: int, pool_ids: Sequence[int], flush: bool = True) -> models.Pool:
    if merged_pool_id in pool_ids:
        raise exceptions.InvalidOperation("Cannot merge a pool into itself")

    if (merged_pool := session.get(models.Pool, merged_pool_id)) is None:
        raise exceptions.ElementDoesNotExist(f"New Pool with id {merged_pool} does not exist")

    from sqlalchemy import orm
    pools = session.query(models.Pool).filter(
        models.Pool.id.in_(pool_ids)
    ).options(orm.joinedload(models.Pool.libraries)).all()

    if len(pool_ids) != len(pools):
        raise exceptions.ElementDoesNotExist("One or more pools to merge do not exist")

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


def remove_library_from_prep(
    session: Session, lab_prep_id: int, library_id: int, flush: bool = True
) -> models.LabPrep:
    if (lab_prep := session.get(models.LabPrep, lab_prep_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
    
    if (library := session.get(models.Library, library_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
    
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
    for adapter in index_kit.adapters:
        for barcode in adapter.barcodes_i7:
            session.delete(barcode)
            
        for barcode in adapter.barcodes_i5:
            session.delete(barcode)

        session.delete(adapter)

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
    dst_sample_mapping = {sample.name: sample for sample in project_dst.samples}

    samples_to_delete = []

    for sample in project_src.samples:
        if sample.name in dst_sample_mapping:
            dst_sample = dst_sample_mapping[sample.name]
            for link in sample.library_links:
                link.sample_id = dst_sample.id
                for attr in sample.attributes:
                    if (dst_attr := dst_sample.get_attribute(attr.name)) is None:
                        dst_sample.set_attribute(attr.name, attr.value, type=attr.type)
                    elif dst_attr.type_id != attr.type_id:
                        raise ValueError(f"Sample attribute conflict for sample '{sample.name}' on attribute '{attr}' with value '{attr.value}' (destination type: '{dst_attr.type}')")
                    elif dst_attr.value != attr.value:
                        raise ValueError(f"Sample attribute conflict for sample '{sample.name}' on attribute '{attr}' with value '{attr.value}' (destination value: '{dst_attr.value}')")
                
                session.add(link)

            dst_sample.qubit_concentration = dst_sample.qubit_concentration or sample.qubit_concentration
            dst_sample.avg_fragment_size = dst_sample.avg_fragment_size or sample.avg_fragment_size
            dst_sample.timestamp_stored_utc = dst_sample.timestamp_stored_utc or sample.timestamp_stored_utc
            dst_sample.status = dst_sample.status if dst_sample.status and dst_sample.status >= sample.status else sample.status
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

    session.add(project_dst)
    return project_dst

def submit_seq_request(session: Session, seq_request: models.SeqRequest) -> models.SeqRequest:
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
