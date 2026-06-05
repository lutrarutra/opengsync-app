from typing import Optional, Literal, Sequence

import sqlalchemy as sa
from sqlalchemy.orm import aliased

from ... import models, queries as Q
from ...categories import (
    LibraryStatus, PoolStatus,
    BarcodeOrientation, SeqRequestStatus, SampleStatus, ProjectStatus, SubmissionType
)
from ... import exceptions
from ..DBBlueprint import DBBlueprint


class ActionsBP(DBBlueprint):
    @DBBlueprint.transaction
    def delete_library(
        self, library: models.Library, delete_orphan_samples: bool = True,
        flush: bool = True
    ):
        if delete_orphan_samples:
            SLL1 = aliased(models.links.SampleLibraryLink)
            SLL2 = aliased(models.links.SampleLibraryLink)

            subquery = (
                self.db.session.query(models.Sample.id)
                .join(SLL1, SLL1.sample_id == models.Sample.id)  # for counting
                .group_by(models.Sample.id)
                .having(sa.func.count(SLL1.library_id) == 1)
                .join(SLL2, SLL2.sample_id == models.Sample.id)  # for filtering by library_id
                .filter(SLL2.library_id == library.id)
                .subquery()
            )

            self.db.session.query(models.Sample).filter(
                models.Sample.id.in_(sa.select(subquery.c.id))
            ).delete(synchronize_session="fetch")

        self.db.session.delete(library)

        if flush:
            self.db.session.flush()
        
        self.delete_orphan(flush=flush)

    @DBBlueprint.transaction
    def delete_orphan(
        self, flush: bool = True
    ) -> None:
        features = self.db.session.query(models.Feature).where(
            models.Feature.feature_kit_id.is_(None),
            ~sa.exists().where(models.links.LibraryFeatureLink.feature_id == models.Feature.id)
        ).all()

        for feature in features:
            self.db.session.delete(feature)

        if flush:
            self.db.session.flush()


    @DBBlueprint.transaction
    def link_sample_library(
        self, sample_id: int, library_id: int,
        mux: Optional[dict] = None,
        flush: bool = True
    ) -> models.links.SampleLibraryLink:
        if self.db.session.query(models.links.SampleLibraryLink).where(
            models.links.SampleLibraryLink.sample_id == sample_id,
            models.links.SampleLibraryLink.library_id == library_id,
        ).first():
            raise exceptions.LinkAlreadyExists(f"Sample with id {sample_id} and Library with id {library_id} are already linked")
        
        link = models.links.SampleLibraryLink(
            sample_id=sample_id,
            library_id=library_id,
            mux=mux,
        )

        self.db.session.add(link)

        if flush:
            self.db.session.flush()

        return link
    
    @DBBlueprint.transaction
    def add_pool_to_lane(
        self, experiment: models.Experiment, pool: models.Pool, lane_num: int, flush: bool = True
    ) -> models.Lane:
        if (lane := self.db.session.query(models.Lane).where(
            models.Lane.experiment_id == experiment.id,
            models.Lane.number == lane_num,
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment.id}")
        
        if self.db.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool.id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first():
            raise exceptions.LinkAlreadyExists(f"Lane with id '{lane.id}' and Pool with id '{pool.id}' are already linked.")
        
        if experiment.workflow.combined_lanes:
            num_m_reads_per_lane = pool.num_m_reads_requested / experiment.num_lanes if pool.num_m_reads_requested else None
        else:
            num_m_reads_per_lane = pool.num_m_reads_requested / (len(pool.lane_links) + 1) if pool.num_m_reads_requested else None

        for link in pool.lane_links:
            link.num_m_reads = num_m_reads_per_lane

        experiment.laned_pool_links.append(
            models.links.LanePoolLink(
                lane_id=lane.id, pool_id=pool.id, experiment_id=experiment.id,
                num_m_reads=num_m_reads_per_lane,
                lane_num=lane_num,
            )
        )
        
        self.db.session.add(pool)
        self.db.session.add(experiment)

        if flush:
            self.db.session.flush()

        return lane
    
    @DBBlueprint.transaction
    def remove_pool_from_lane(self, experiment: models.Experiment, pool: models.Pool, lane_num: int, flush: bool = True) -> models.Lane:
        if (lane := self.db.session.query(models.Lane).where(
            models.Lane.experiment_id == experiment.id,
            models.Lane.number == lane_num,
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment.id}")
        
        if (link := self.db.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool.id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first()) is None:
            raise exceptions.LinkDoesNotExist(f"Lane with id '{lane.id}' and Pool with id '{pool.id}' are not linked.")
        
        experiment.laned_pool_links.remove(link)
        
        for _link in pool.lane_links:
            if _link.lane_id == lane.id:
                continue
            _link.num_m_reads = pool.num_m_reads_requested / len(pool.lane_links) if pool.num_m_reads_requested else None

        self.db.session.add(lane)
        self.db.session.add(pool)
        self.db.session.add(experiment)

        if flush:
            self.db.session.flush()
        return lane
    
    @DBBlueprint.transaction
    def unlink_pool_experiment(self, experiment_id: int, pool_id: int, flush: bool = True):
        if (experiment := self.db.session.get(models.Experiment, experiment_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        if pool.experiment_id != experiment_id:
            raise exceptions.LinkDoesNotExist(f"Pool with id {pool_id} is not linked to experiment with id {experiment_id}")
        
        for lane in experiment.lanes:
            if (link := self.db.session.query(models.links.LanePoolLink).where(
                models.links.LanePoolLink.pool_id == pool_id,
                models.links.LanePoolLink.lane_id == lane.id,
            ).first()) is not None:
                self.db.session.delete(link)

        for library in pool.libraries:
            library.experiment_id = None

        experiment.pools.remove(pool)
        self.db.session.add(pool)
        self.db.session.add(experiment)

        if flush:
            self.db.session.flush()


    @DBBlueprint.transaction
    def clone_library(
        self, library_id: int, seq_request_id: int, indexed: bool, status: LibraryStatus
    ) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
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
            self.link_sample_library(
                sample_id=sample_link.sample_id,
                library_id=cloned_library.id,
                mux=sample_link.mux if sample_link.mux is not None else None,
            )

        for feature in library.features:
            self.link_feature_library(
                feature_id=feature.id,
                library_id=cloned_library.id
            )

        if indexed:
            for index in library.indices:
                self.add_index_to_library(
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
    

    @DBBlueprint.transaction
    def add_index_to_library(
        self, library_id: int,
        index_kit_i7_id: Optional[int], name_i7: Optional[str], sequence_i7: Optional[str],
        index_kit_i5_id: Optional[int], name_i5: Optional[str], sequence_i5: Optional[str],
        orientation: Optional[BarcodeOrientation],
        flush: bool = True
    ) -> models.Library:

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        if index_kit_i7_id is not None:
            if self.db.session.get(models.IndexKit, index_kit_i7_id) is None:
                raise exceptions.ElementDoesNotExist(f"Index kit with id {index_kit_i7_id} does not exist")
            
        if index_kit_i5_id is not None:
            if self.db.session.get(models.IndexKit, index_kit_i5_id) is None:
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

        self.db.session.add(library)

        if flush:
            self.db.session.flush()

        return library
    
    @DBBlueprint.transaction
    def link_feature_library(self, feature_id: int, library_id: int):
        if (feature := self.db.session.get(models.Feature, feature_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
        
        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        if self.db.session.query(models.links.LibraryFeatureLink).where(
            models.links.LibraryFeatureLink.feature_id == feature_id,
            models.links.LibraryFeatureLink.library_id == library_id,
        ).first():
            raise exceptions.LinkAlreadyExists(f"Feature with id {feature_id} and Library with id {library_id} are already linked")
        
        library.features.append(feature)
        self.db.session.add(library)


    @DBBlueprint.transaction
    def process_seq_request(self, seq_request_id: int, status: SeqRequestStatus) -> models.SeqRequest:
        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")

        seq_request.status = status

        if seq_request.status in [SeqRequestStatus.DRAFT, SeqRequestStatus.REJECTED]:
            seq_request.timestamp_submitted_utc = None
            if seq_request.sample_submission_event is not None:
                self.db.session.delete(seq_request.sample_submission_event)
                seq_request.sample_submission_event = None
        
        if status == SeqRequestStatus.ACCEPTED:
            library_status = LibraryStatus.ACCEPTED
            pool_status = PoolStatus.ACCEPTED
        elif status == SeqRequestStatus.DRAFT:
            library_status = LibraryStatus.DRAFT
            pool_status = PoolStatus.DRAFT
        elif status == SeqRequestStatus.REJECTED:
            library_status = LibraryStatus.REJECTED
            pool_status = PoolStatus.REJECTED
        else:
            raise TypeError(f"Cannot process request to '{status}'.")

        for sample in seq_request.samples:
            if sample.status != SampleStatus.DRAFT:
                continue  # Sample was not prepared in-house -> no specimen stored
            if status == SeqRequestStatus.ACCEPTED:
                sample.status = SampleStatus.WAITING_DELIVERY
            elif status == SeqRequestStatus.DRAFT:
                sample.status = SampleStatus.DRAFT
            elif status == SeqRequestStatus.REJECTED:
                sample.status = SampleStatus.REJECTED
        
        is_prepared = status == SeqRequestStatus.ACCEPTED
        for library in seq_request.libraries:
            if library.status == LibraryStatus.SUBMITTED:
                library.status = library_status
            if library_status != LibraryStatus.ACCEPTED:
                continue
            
            if library.pool_id is not None:
                library.status = LibraryStatus.POOLED

            is_prepared = is_prepared and library.status.id >= LibraryStatus.POOLED.id
        
        if status == SeqRequestStatus.ACCEPTED:
            seq_request.status = SeqRequestStatus.ACCEPTED

        for pool in seq_request.pools:
            if pool.status != PoolStatus.SUBMITTED:
                continue
            pool.status = pool_status

        if status == SeqRequestStatus.ACCEPTED:
            for project in seq_request.projects:
                project.status = ProjectStatus.PROCESSING
                self.db.session.add(project)

        self.db.session.add(seq_request)
        return seq_request
    
    @DBBlueprint.transaction
    def clone_seq_request(self, seq_request_id: int, method: Literal["pooled", "indexed", "raw"]) -> models.SeqRequest:
        if method not in {"pooled", "indexed", "raw"}:
            raise ValueError(f"Method should be one of: {', '.join(['pooled', 'indexed', 'raw'])}")

        if (seq_request := self.db.session.get(models.SeqRequest, seq_request_id)) is None:
            raise exceptions.ElementDoesNotExist(f"SeqRequest with id '{seq_request_id}', not found.")
        
        if method == "raw":
            submission_type = SubmissionType.RAW_SAMPLES
        elif method == "indexed":
            submission_type = SubmissionType.UNPOOLED_LIBRARIES
        elif method == "pooled":
            submission_type = SubmissionType.POOLED_LIBRARIES

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
                cloned_library = self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=LibraryStatus.POOLED)
                if library.pool_id is not None:
                    if library.pool_id not in pools.keys():
                        pools[library.pool_id] = self.clone_pool(library.pool_id, seq_request_id=cloned_request.id, status=PoolStatus.STORED)
                    cloned_library.pool_id = pools[library.pool_id].id
        elif method == "indexed":
            for library in seq_request.libraries:
                self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=True, status=LibraryStatus.STORED)
        elif method == "raw":
            for library in seq_request.libraries:
                self.clone_library(library_id=library.id, seq_request_id=cloned_request.id, indexed=False, status=LibraryStatus.ACCEPTED)

        self.db.session.add(cloned_request)
        return cloned_request
    
    @DBBlueprint.transaction
    def clone_pool(self, pool_id: int, status: PoolStatus, seq_request_id: int | None = None) -> models.Pool:

        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
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
    
    @DBBlueprint.transaction
    def merge_pool(self, merged_pool_id: int, pool_ids: Sequence[int], flush: bool = True) -> models.Pool:
        if merged_pool_id in pool_ids:
            raise exceptions.InvalidOperation("Cannot merge a pool into itself")

        if (merged_pool := self.db.session.get(models.Pool, merged_pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"New Pool with id {merged_pool} does not exist")

        from sqlalchemy import orm
        pools = self.db.session.query(models.Pool).filter(
            models.Pool.id.in_(pool_ids)
        ).options(orm.joinedload(models.Pool.libraries)).all()

        if len(pool_ids) != len(pools):
            raise exceptions.ElementDoesNotExist("One or more pools to merge do not exist")

        for pool in pools:
            for library in pool.libraries:
                library.pool_id = merged_pool.id

            pool.status = PoolStatus.REPOOLED
            pool.merged_to_pool_id = merged_pool.id
            self.db.session.add(pool)

        self.db.session.add(merged_pool)

        if flush:
            self.db.session.flush()
        return merged_pool
    

    @DBBlueprint.transaction
    def remove_library_from_prep(
        self, lab_prep_id: int, library_id: int, flush: bool = True
    ) -> models.LabPrep:
        if (lab_prep := self.db.session.get(models.LabPrep, lab_prep_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Lab prep with id '{lab_prep_id}', not found.")
        
        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id '{library_id}', not found.")
        
        if library.status == LibraryStatus.PREPARING:
            library.status = LibraryStatus.ACCEPTED
        
        lab_prep.libraries.remove(library)
        self.db.session.add(lab_prep)
        if flush:
            self.db.session.flush()
        return lab_prep