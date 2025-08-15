import math
from typing import Optional

from ... import models, PAGE_LIMIT
from .. import exceptions

from ..DBBlueprint import DBBlueprint


class LinkBP(DBBlueprint):
    @DBBlueprint.transaction
    def get_sample_library_link(
        self, sample_id: int, library_id: int,
    ) -> models.links.SampleLibraryLink | None:
        link = self.db.session.query(models.links.SampleLibraryLink).where(
            models.links.SampleLibraryLink.sample_id == sample_id,
            models.links.SampleLibraryLink.library_id == library_id,
        ).first()
        return link

    @DBBlueprint.transaction
    def update_sample_library_link(
        self, link: models.links.SampleLibraryLink,
    ) -> models.links.SampleLibraryLink:
        self.db.session.add(link)
        return link

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
            self.db.flush()

        return link

    @DBBlueprint.transaction
    def unlink_sample_library(self, sample_id: int, library_id: int, flush: bool = True):
        if (link := self.db.session.query(models.links.SampleLibraryLink).where(
            models.links.SampleLibraryLink.sample_id == sample_id,
            models.links.SampleLibraryLink.library_id == library_id,
        ).first()) is None:
            raise exceptions.LinkDoesNotExist(f"Sample with id {sample_id} and Library with id {library_id} are not linked")

        self.db.session.delete(link)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def get_sample_library_links(
        self,
        sample_id: int | None = None,
        library_id: int | None = None,
        seq_request_id: int | None = None,
        limit: int | None = PAGE_LIMIT,
        offset: int | None = None,
        count_pages: bool = False,
    ) -> tuple[list[models.links.SampleLibraryLink], int | None]:
        query = self.db.session.query(models.links.SampleLibraryLink)
        if sample_id is not None:
            query = query.where(models.links.SampleLibraryLink.sample_id == sample_id)

        if library_id is not None:
            query = query.where(models.links.SampleLibraryLink.library_id == library_id)

        if seq_request_id is not None:
            query = query.join(
                models.Library,
                models.Library.id == models.links.SampleLibraryLink.library_id,
            ).where(
                models.Library.seq_request_id == seq_request_id,
            )
        
        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        links = query.all()
        return links, n_pages

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
    def link_features_library(
        self, feature_ids: list[int], library_id: int,
        flush: bool = True
    ) -> models.Library:
        ids = set(feature_ids)

        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        features = self.db.session.query(models.Feature).where(
            models.Feature.id.in_(ids)
        ).all()

        library.features.extend(features)
        self.db.session.add(library)

        if flush:
            self.db.flush()

        return library

    @DBBlueprint.transaction
    def unlink_sample_from_library(self, sample_id: int, library_id: int):
        if (link := self.db.session.query(models.links.SampleLibraryLink).where(
            models.links.SampleLibraryLink.sample_id == sample_id,
            models.links.SampleLibraryLink.library_id == library_id,
        ).first()) is None:
            raise exceptions.LinkDoesNotExist(f"Sample with id {sample_id} and Library with id {library_id} are not linked")
    
        self.db.session.delete(link)

    @DBBlueprint.transaction
    def unlink_feature_library(self, feature_id: int, library_id: int):
        if (feature := self.db.session.get(models.Feature, feature_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Feature with id {feature_id} does not exist")
        
        if (library := self.db.session.get(models.Library, library_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Library with id {library_id} does not exist")
        
        library.features.remove(feature)
        self.db.session.add(library)

    @DBBlueprint.transaction
    def add_pool_to_lane(
        self, experiment_id: int, pool_id: int, lane_num: int, flush: bool = True
    ) -> models.Lane:
        if (experiment := self.db.session.get(models.Experiment, experiment_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")

        if (lane := self.db.session.query(models.Lane).where(
            models.Lane.experiment_id == experiment_id,
            models.Lane.number == lane_num,
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment_id}")
        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        
        if self.db.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool_id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first():
            raise exceptions.LinkAlreadyExists(f"Lane with id '{lane.id}' and Pool with id '{pool_id}' are already linked.")
        
        if experiment.workflow.combined_lanes:
            num_m_reads_per_lane = pool.num_m_reads_requested / experiment.num_lanes if pool.num_m_reads_requested else None
        else:
            num_m_reads_per_lane = pool.num_m_reads_requested / (len(pool.lane_links) + 1) if pool.num_m_reads_requested else None

        for link in pool.lane_links:
            link.num_m_reads = num_m_reads_per_lane
            self.db.session.add(link)
        
        link = models.links.LanePoolLink(
            lane_id=lane.id, pool_id=pool_id, experiment_id=experiment_id,
            num_m_reads=num_m_reads_per_lane,
            lane_num=lane_num,
        )
        
        self.db.session.add(link)

        if flush:
            self.db.flush()

        return lane

    @DBBlueprint.transaction
    def remove_pool_from_lane(self, experiment_id: int, pool_id: int, lane_num: int, flush: bool = True) -> models.Lane:
        if (lane := self.db.session.query(models.Lane).where(
            models.Lane.experiment_id == experiment_id,
            models.Lane.number == lane_num,
        ).first()) is None:
            raise exceptions.ElementDoesNotExist(f"Lane with number {lane_num} does not exist in experiment with id {experiment_id}")
        
        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        
        if (link := self.db.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.pool_id == pool_id,
            models.links.LanePoolLink.lane_id == lane.id,
        ).first()) is None:
            raise exceptions.LinkDoesNotExist(f"Lane with id '{lane.id}' and Pool with id '{pool_id}' are not linked.")
        
        self.db.session.delete(link)
        
        for _link in pool.lane_links:
            if _link.lane_id == lane.id:
                continue
            _link.num_m_reads = pool.num_m_reads_requested / len(pool.lane_links) if pool.num_m_reads_requested else None
            self.db.session.add(_link)

        self.db.session.add(lane)

        if flush:
            self.db.flush()
        return lane

    @DBBlueprint.transaction
    def link_pool_experiment(self, experiment_id: int, pool_id: int, flush: bool = True):
        if (experiment := self.db.session.get(models.Experiment, experiment_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        if pool.experiment_id is not None:
            raise exceptions.LinkAlreadyExists(f"Pool with id {pool_id} is already linked to an experiment")

        experiment.pools.append(pool)

        for library in pool.libraries:
            library.experiment_id = experiment_id

        if experiment.workflow.combined_lanes:
            for lane in experiment.lanes:
                self.add_pool_to_lane(experiment_id=experiment_id, pool_id=pool_id, lane_num=lane.number)

        self.db.session.add(experiment)
        self.db.session.add(pool)
        
        if flush:
            self.db.flush()

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
            self.db.flush()

    @DBBlueprint.transaction
    def get_laned_pool_link(
        self, experiment_id: int, lane_num: int, pool_id: int,
    ) -> models.links.LanePoolLink | None:
        link = self.db.session.query(models.links.LanePoolLink).where(
            models.links.LanePoolLink.experiment_id == experiment_id,
            models.links.LanePoolLink.lane_num == lane_num,
            models.links.LanePoolLink.pool_id == pool_id,
        ).first()
        return link

    def update_laned_pool_link(
        self, link: models.links.LanePoolLink,
    ) -> models.links.LanePoolLink:
        self.db.session.add(link)
        return link