import math
from typing import Optional

from sqlalchemy.sql.operators import and_

from ... import models, PAGE_LIMIT
from .. import exceptions


def create_adapter(
    self, name: str, index_kit_id: int,
    plate_well: Optional[str] = None,
    barcode_1_id: Optional[int] = None,
    barcode_2_id: Optional[int] = None,
    barcode_3_id: Optional[int] = None,
    barcode_4_id: Optional[int] = None,
    commit: bool = True
) -> models.Adapter:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.query(models.Adapter).where(
        and_(
            models.Adapter.name == name,
            models.Adapter.index_kit_id == index_kit_id
        )
    ).first():
        raise exceptions.NotUniqueValue(f"adapter with name '{name}', already exists.")
    
    if self._session.query(models.Adapter).where(
        and_(
            models.Adapter.plate_well == plate_well,
            models.Adapter.index_kit_id == index_kit_id
        )
    ).first():
        raise exceptions.NotUniqueValue(f"adapter with plate_well '{plate_well}', already exists.")

    adapter = models.Adapter(
        name=name.strip(),
        plate_well=plate_well,
        index_kit_id=index_kit_id,
        barcode_1_id=barcode_1_id,
        barcode_2_id=barcode_2_id,
        barcode_3_id=barcode_3_id,
        barcode_4_id=barcode_4_id
    )

    self._session.add(adapter)

    if commit:
        self._session.commit()
        self._session.refresh(adapter)

    if not persist_session:
        self.close_session()

    return adapter


def get_adapter(self, id: int) -> Optional[models.Adapter]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Adapter, id)

    if not persist_session:
        self.close_session()

    return res


def get_adapters(
    self, index_kit_id: Optional[int] = None,
    sort_by: Optional[str] = None, descending: bool = False,
    limit: Optional[int] = PAGE_LIMIT, offset: Optional[int] = None,

) -> tuple[list[models.Adapter], int]:
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Adapter)

    if index_kit_id is not None:
        query = query.where(models.Adapter.index_kit_id == index_kit_id)

    n_pages: int = math.ceil(query.count() / limit) if limit is not None else 1

    if sort_by is not None:
        attr = getattr(models.Adapter, sort_by)
        if descending:
            attr = attr.desc()
        query = query.order_by(attr)

    if limit is not None:
        query = query.limit(limit)

    if offset is not None:
        query = query.offset(offset)

    res = query.all()

    if not persist_session:
        self.close_session()

    return res, n_pages


def get_adapter_from_index_kit(
    self, index_kit_id: int,
    adapter: Optional[str] = None,
    plate_well: Optional[str] = None
) -> models.Adapter:
    
    if plate_well is not None and adapter is not None:
        raise ValueError("Both 'adapter' and 'plate_well' cannot be provided at the same time.")
    elif plate_well is None and adapter is None:
        raise ValueError("Either 'adapter' or 'plate_well' must be provided.")
    elif plate_well is not None:
        fltr = and_(
            models.Adapter.plate_well == plate_well,
            models.Adapter.index_kit_id == index_kit_id
        )
    else:
        fltr = and_(
            models.Adapter.name == adapter,
            models.Adapter.index_kit_id == index_kit_id
        )
    
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.query(models.Adapter).where(fltr).first()

    if not persist_session:
        self.close_session()

    return res