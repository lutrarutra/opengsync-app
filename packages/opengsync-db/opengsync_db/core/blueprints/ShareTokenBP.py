import math
from typing import Callable

from sqlalchemy.orm import Query
from sqlalchemy.sql.base import ExecutableOption

from ..DBBlueprint import DBBlueprint
from ... import models, PAGE_LIMIT
from .. import exceptions


class ShareTokenBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query,
        owner_id: int | None = None,
        custom_query: Callable | None = None,
    ):
        if owner_id is not None:
            query = query.where(models.ShareToken.owner_id == owner_id)

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self,
        owner: models.User,
        time_valid_min: int,
        paths: list[str],
        flush: bool = True,
    ) -> models.ShareToken:
        token = models.ShareToken(
            owner=owner,
            time_valid_min=time_valid_min,
        )
        for path in paths:
            token.paths.append(models.SharePath(path=path))

        self.db.session.add(token)

        if flush:
            self.db.flush()
        return token

    @DBBlueprint.transaction
    def get(self, uuid: str, options: ExecutableOption | None = None) -> models.ShareToken | None:
        if options is None:
            token = self.db.session.query(models.ShareToken).filter(models.ShareToken.uuid == uuid).first()
        else:
            token = self.db.session.query(models.ShareToken).options(options).filter(models.ShareToken.uuid == uuid).first()
        return token

    @DBBlueprint.transaction
    def find(
        self,
        owner: models.User | None = None,
        sort_by: str | None = None, descending: bool = False,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        page: int | None = None,
        custom_query: Callable[[Query], Query] | None = None,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.ShareToken], int | None]:
        query = self.db.session.query(models.ShareToken)

        query = ShareTokenBP.where(query, owner_id=owner.id if owner is not None else None)
        if custom_query is not None:
            query = custom_query(query)

        if options is not None:
            query = query.options(options)

        if sort_by is not None:
            attr = getattr(models.ShareToken, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)
        
        if page is not None:
            if limit is None:
                raise ValueError("Limit must be provided when page is provided")
            
            count = query.count()
            n_pages = math.ceil(count / limit)
            query = query.offset(min(page, max(0, n_pages - 1)) * limit)
        else:
            n_pages = None

        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        tokens = query.all()
        return tokens, n_pages

    @DBBlueprint.transaction
    def update(self, token: models.ShareToken):
        self.db.session.add(token)

    @DBBlueprint.transaction
    def delete(self, token: models.ShareToken):
        self.db.session.delete(token)
    
    @DBBlueprint.transaction
    def __getitem__(self, uuid: str) -> models.ShareToken:
        if (token := self.get(uuid)) is None:
            raise exceptions.ElementDoesNotExist(f"ShareToken with ID/UUID '{uuid}' not found.")
        return token