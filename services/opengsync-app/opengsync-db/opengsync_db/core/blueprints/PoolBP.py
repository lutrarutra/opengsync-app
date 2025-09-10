import math
import string
from typing import Optional, Sequence, Callable

import sqlalchemy as sa
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.orm import Query
    
from ...categories import PoolStatus, PoolStatusEnum, PoolTypeEnum, AccessType, AccessTypeEnum
from ... import PAGE_LIMIT, models
from .. import exceptions
from ..DBBlueprint import DBBlueprint


class PoolBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query: Query,
        user_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
        seq_request_id: int | None = None,
        associated_to_experiment: Optional[bool] = None,
        status: Optional[PoolStatusEnum] = None,
        status_in: Optional[list[PoolStatusEnum]] = None,
        type_in: Optional[list[PoolTypeEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
    ) -> Query:
        if user_id is not None:
            query = query.where(
                models.Pool.owner_id == user_id
            )

        if library_id is not None:
            query = query.where(
                sa.exists().where(
                    (models.Library.pool_id == models.Pool.id) &
                    (models.Library.id == library_id)
                )
            )

        if experiment_id is not None:
            query = query.where(models.Pool.experiment_id == experiment_id)

        if seq_request_id is not None:
            query = query.where(models.Pool.seq_request_id == seq_request_id)

        if lab_prep_id is not None:
            query = query.where(models.Pool.lab_prep_id == lab_prep_id)

        if status is not None:
            query = query.where(models.Pool.status_id == status.id)

        if status_in is not None:
            query = query.where(models.Pool.status_id.in_([s.id for s in status_in]))

        if type_in is not None:
            query = query.where(models.Pool.type_id.in_([t.id for t in type_in]))

        if associated_to_experiment is not None:
            if associated_to_experiment:
                query = query.where(models.Pool.experiment_id.isnot(None))
            else:
                query = query.where(models.Pool.experiment_id.is_(None))

        if custom_query is not None:
            query = custom_query(query)

        return query

    @DBBlueprint.transaction
    def create(
        self, name: str,
        owner_id: int,
        contact_name: str,
        contact_email: str,
        pool_type: PoolTypeEnum,
        experiment_id: int | None = None,
        original_pool_id: int | None = None,
        seq_request_id: int | None = None,
        lab_prep_id: int | None = None,
        num_m_reads_requested: Optional[float] = None,
        status: PoolStatusEnum = PoolStatus.DRAFT,
        contact_phone: Optional[str] = None,
        flush: bool = True
    ) -> models.Pool:
        
        if seq_request_id is not None:
            if self.db.session.get(models.SeqRequest, seq_request_id) is None:
                raise exceptions.ElementDoesNotExist(f"SeqRequest with id {seq_request_id} does not exist")
            
        if experiment_id is not None:
            if self.db.session.get(models.Experiment, experiment_id) is None:
                raise exceptions.ElementDoesNotExist(f"Experiment with id {experiment_id} does not exist")
            
        if lab_prep_id is not None:
            if self.db.session.get(models.LabPrep, lab_prep_id) is None:
                raise exceptions.ElementDoesNotExist(f"LabPrep with id {lab_prep_id} does not exist")
            
        if original_pool_id is not None:
            if self.db.session.get(models.Pool, original_pool_id) is None:
                raise exceptions.ElementDoesNotExist(f"Original Pool with id {original_pool_id} does not exist")
            clone_number = self.get_number_of_cloned_pools(original_pool_id) + 1
        else:
            clone_number = 0
            
        pool = models.Pool(
            name=name.strip(),
            owner_id=owner_id,
            type_id=pool_type.id,
            seq_request_id=seq_request_id,
            num_m_reads_requested=num_m_reads_requested,
            contact=models.Contact(
                name=contact_name.strip(),
                email=contact_email.strip(),
                phone=contact_phone.strip() if contact_phone else None
            ),
            lab_prep_id=lab_prep_id,
            status_id=status.id,
            timestamp_stored_utc=sa.func.now() if status == PoolStatus.STORED else None,
            clone_number=clone_number,
            original_pool_id=original_pool_id,
            experiment_id=experiment_id
        )
        
        self.db.session.add(pool)

        if flush:
            self.db.flush()

        return pool

    @DBBlueprint.transaction
    def get(self, pool_id: int, options: ExecutableOption | None = None) -> models.Pool | None:
        if options is not None:
            pool = self.db.session.query(models.Pool).options(options).filter(models.Pool.id == pool_id).first()
        else:
            pool = self.db.session.get(models.Pool, pool_id)
        return pool

    @DBBlueprint.transaction
    def find(
        self,
        user_id: int | None = None,
        library_id: int | None = None,
        experiment_id: int | None = None,
        lab_prep_id: int | None = None,
        seq_request_id: int | None = None,
        associated_to_experiment: Optional[bool] = None,
        status: Optional[PoolStatusEnum] = None,
        status_in: Optional[list[PoolStatusEnum]] = None,
        type_in: Optional[list[PoolTypeEnum]] = None,
        custom_query: Callable[[Query], Query] | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        count_pages: bool = False,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.Pool], int | None]:

        query = self.db.session.query(models.Pool)

        query = PoolBP.where(
            query,
            user_id=user_id,
            library_id=library_id,
            experiment_id=experiment_id,
            lab_prep_id=lab_prep_id,
            seq_request_id=seq_request_id,
            associated_to_experiment=associated_to_experiment,
            status=status,
            status_in=status_in,
            type_in=type_in,
            custom_query=custom_query
        )
        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.Pool, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None
        
        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        pools = query.all()
        return pools, n_pages

    @DBBlueprint.transaction
    def delete(self, pool_id: int, flush: bool = True):
        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

        self.db.session.delete(pool)

        if flush:
            self.db.flush()

    @DBBlueprint.transaction
    def update(self, pool: models.Pool):
        self.db.session.add(pool)

    @DBBlueprint.transaction
    def dilute(
        self,
        pool_id: int,
        qubit_concentration: float,
        operator_id: int,
        volume_ul: Optional[float] = None,
        flush: bool = True
    ) -> models.Pool:

        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
            
        n = len(pool.dilutions)

        def to_identifier(n: int) -> str:
            out = ""

            while n >= 0:
                n, r = divmod(n, 26)
                out = string.ascii_uppercase[r] + out
                n -= 1

            return out

        dilution = models.PoolDilution(
            pool_id=pool_id,
            operator_id=operator_id,
            identifier=to_identifier(n),
            qubit_concentration=qubit_concentration,
            volume_ul=volume_ul,
        )

        pool.dilutions.append(dilution)
        self.db.session.add(pool)
        self.db.session.refresh(pool)
        
        if flush:
            self.db.flush()

        return pool

    @DBBlueprint.transaction
    def query(
        self, name: str, experiment_id: int | None = None,
        seq_request_id: int | None = None,
        status_in: Optional[list[PoolStatusEnum]] = None,
        limit: int | None = PAGE_LIMIT
    ) -> list[models.Pool]:

        query = self.db.session.query(models.Pool)

        if experiment_id is not None:
            query = query.where(
                models.Pool.experiment_id == experiment_id
            )

        if seq_request_id is not None:
            query = query.where(
                models.Pool.seq_request_id == seq_request_id
            )

        if status_in is not None:
            query = query.where(
                models.Pool.status_id.in_([s.id for s in status_in])
            )

        query = query.order_by(
            sa.func.similarity(models.Pool.name, name).desc()
        )

        if limit is not None:
            query = query.limit(limit)

        pools = query.all()

        return pools

    @DBBlueprint.transaction
    def get_dilution(self, pool_id: int, identifier: str) -> models.PoolDilution | None:
        dilution = self.db.session.query(models.PoolDilution).where(
            models.PoolDilution.pool_id == pool_id,
            models.PoolDilution.identifier == identifier
        ).first()
        return dilution

    @DBBlueprint.transaction
    def get_dilutions(
        self, pool_id: int | None = None,
        experiment_id: int | None = None,
        sort_by: Optional[str] = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        count_pages: bool = False
    ) -> tuple[list[models.PoolDilution], int | None]:

        if pool_id is not None and experiment_id is not None:
            raise Exception("Cannot filter by both pool_id and experiment_id")

        query = self.db.session.query(models.PoolDilution)
        if pool_id is not None:
            query = query.where(
                models.PoolDilution.pool_id == pool_id
            )

        if experiment_id is not None:
            query = query.join(
                models.Pool,
                models.Pool.id == models.PoolDilution.pool_id
            ).where(
                models.Pool.experiment_id == experiment_id
            )

        if sort_by is not None:
            attr = getattr(models.PoolDilution, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None
        
        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        dilutions = query.all()
        return dilutions, n_pages

    @DBBlueprint.transaction
    def get_number_of_cloned_pools(self, original_pool_id: int) -> int:
        count = self.db.session.query(models.Pool).where(
            models.Pool.original_pool_id == original_pool_id
        ).count()
        return count

    @DBBlueprint.transaction
    def get_access_type(self, pool: models.Pool, user: models.User) -> AccessTypeEnum:
        if user.is_admin():
            return AccessType.ADMIN
        if user.is_insider():
            return AccessType.INSIDER
        if pool.owner_id == user.id:
            return AccessType.OWNER

        if pool.seq_request is not None:
            has_access: bool = self.db.session.query(
                sa.exists().where(
                    (models.links.UserAffiliation.user_id == user.id) &
                    (models.links.UserAffiliation.group_id == pool.seq_request.group_id)
                )
            ).scalar()
            if has_access:
                return AccessType.EDIT

        return AccessType.NONE

    @DBBlueprint.transaction
    def clone(self, pool_id: int, status: PoolStatusEnum, seq_request_id: int | None = None) -> models.Pool:

        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")

        cloned_pool = self.create(
            name=pool.name,
            owner_id=pool.owner_id,
            seq_request_id=seq_request_id,
            num_m_reads_requested=pool.num_m_reads_requested,
            lab_prep_id=pool.lab_prep_id,
            contact_email=pool.contact.email if pool.contact.email is not None else "unknown",
            contact_name=pool.contact.name,
            contact_phone=pool.contact.phone,
            pool_type=pool.type,
            original_pool_id=pool.original_pool_id if pool.original_pool_id is not None else pool.id,
            status=status,
        )
        return cloned_pool

    @DBBlueprint.transaction
    def merge(self, merged_pool_id: int, pool_ids: Sequence[int], flush: bool = True) -> models.Pool:
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
            self.db.session.add(pool)

        self.db.session.add(merged_pool)
        
        self.db.session.query(models.Pool).filter(
            models.Pool.id.in_(pool_ids)
        ).delete()

        if flush:
            self.db.flush()
        return merged_pool
    
    @DBBlueprint.transaction
    def __getitem__(self, pool_id: int) -> models.Pool:
        """Get a pool by its ID."""
        if (pool := self.db.session.get(models.Pool, pool_id)) is None:
            raise exceptions.ElementDoesNotExist(f"Pool with id {pool_id} does not exist")
        return pool




        
        
        
