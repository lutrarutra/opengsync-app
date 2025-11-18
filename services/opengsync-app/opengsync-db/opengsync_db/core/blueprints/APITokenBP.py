import math
from typing import Callable

from sqlalchemy.sql.base import ExecutableOption

from ..DBBlueprint import DBBlueprint
from ... import models, PAGE_LIMIT
from .. import exceptions


class APITokenBP(DBBlueprint):
    @classmethod
    def where(
        cls,
        query,
        owner_id: int | None = None,
        custom_query: Callable | None = None,
    ):
        if owner_id is not None:
            query = query.where(models.APIToken.owner_id == owner_id)

        if custom_query is not None:
            query = custom_query(query)

        return query
    
    @DBBlueprint.transaction
    def create(
        self,
        owner: models.User,
        time_valid_min: int,
        flush: bool = True,
    ) -> models.APIToken:
        token = models.APIToken(
            owner=owner,
            time_valid_min=time_valid_min,
        )

        self.db.session.add(token)

        if flush:
            self.db.flush()
        return token

    @DBBlueprint.transaction
    def get(self, id: int | str, options: ExecutableOption | None = None) -> models.APIToken | None:
        if options is None:
            if isinstance(id, int):
                token = self.db.session.get(models.APIToken, id)
            elif isinstance(id, str):
                token = self.db.session.query(models.APIToken).filter(models.APIToken.uuid == id).first()
        else:
            if isinstance(id, int):
                token = self.db.session.query(models.APIToken).options(options).filter(models.APIToken.id == id).first()
            elif isinstance(id, str):
                token = self.db.session.query(models.APIToken).options(options).filter(models.APIToken.uuid == id).first()
        return token

    @DBBlueprint.transaction
    def find(
        self,
        owner: models.User | None = None,
        limit: int | None = PAGE_LIMIT, offset: int | None = None,
        sort_by: str | None = None, descending: bool = False,
        count_pages: bool = False,
        options: ExecutableOption | None = None,
    ) -> tuple[list[models.APIToken], int | None]:
        query = self.db.session.query(models.APIToken)

        query = APITokenBP.where(query, owner_id=owner.id if owner is not None else None)
        if options is not None:
            query = query.options(options)

        n_pages = None if not count_pages else math.ceil(query.count() / limit) if limit is not None else None

        if sort_by is not None:
            attr = getattr(models.APIToken, sort_by)
            if descending:
                attr = attr.desc()
            query = query.order_by(attr)
        
        if offset is not None:
            query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        tokens = query.all()
        return tokens, n_pages

    @DBBlueprint.transaction
    def update(self, token: models.APIToken):
        self.db.session.add(token)

    @DBBlueprint.transaction
    def delete(self, token: models.APIToken):
        self.db.session.delete(token)
    
    @DBBlueprint.transaction
    def __getitem__(self, key: int | str) -> models.APIToken:
        if (token := self.get(key)) is None:
            raise exceptions.ElementDoesNotExist(f"API Token with ID/UUID '{key}' not found.")
        return token