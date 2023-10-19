from typing import Optional

import pandas as pd
from sqlmodel import and_

from ... import models, logger
from .. import exceptions
from ...tools import SearchResult


def create_sample(
    self, name: str,
    organism_tax_id: int,
    owner_id: int,
    project_id: int,
    commit: bool = True
) -> models.Sample:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if (_ := self._session.get(models.Project, project_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Project with id '{project_id}', not found.")

    if (organism := self._session.get(models.Organism, organism_tax_id)) is None:
        raise exceptions.ElementDoesNotExist(f"Organism with tax_id '{organism_tax_id}', not found.")
    
    if (_ := self._session.get(models.User, owner_id)) is None:
        raise exceptions.ElementDoesNotExist(f"User with id '{owner_id}', not found.")

    sample = models.Sample(
        name=name,
        organism_id=organism.tax_id,
        project_id=project_id,
        owner_id=owner_id
    )

    self._session.add(sample)
    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def get_sample(self, sample_id: int) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    res = self._session.get(models.Sample, sample_id)

    if not persist_session:
        self.close_session()
    return res


def get_num_samples(self, user_id: Optional[int] = None) -> int:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample)
    if user_id is not None:
        query = query.where(
            models.Sample.owner_id == user_id
        )

    res = query.count()

    if not persist_session:
        self.close_session()
    return res


def get_samples(
    self, limit: Optional[int] = 20, offset: Optional[int] = None,
    user_id: Optional[int] = None
) -> list[models.Sample]:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample).order_by(models.Sample.id.desc())
    if user_id is not None:
        query = query.where(
            models.Sample.owner_id == user_id
        )

    if offset is not None:
        query = query.offset(offset)

    if limit is not None:
        query = query.limit(limit)

    samples = query.all()

    if not persist_session:
        self.close_session()
    return samples


def get_sample_by_name(self, name: str) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.query(models.Sample).filter_by(name=name).first()
    if not persist_session:
        self.close_session()
    return sample


def update_sample(
    self, sample_id: int,
    name: Optional[str] = None,
    organism_tax_id: Optional[int] = None,
    commit: bool = True
) -> models.Sample:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    if organism_tax_id is not None:
        if (organism := self._session.get(models.Organism, organism_tax_id)) is not None:
            sample.organism_id = organism_tax_id
            sample.organism = organism
        else:
            raise exceptions.ElementDoesNotExist(f"Organism with id {organism_tax_id} does not exist")

    if name is not None:
        sample.name = name

    if commit:
        self._session.commit()
        self._session.refresh(sample)

    if not persist_session:
        self.close_session()
    return sample


def delete_sample(
    self, sample_id: int,
    commit: bool = True
) -> None:
    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    sample = self._session.get(models.Sample, sample_id)
    if not sample:
        raise exceptions.ElementDoesNotExist(f"Sample with id {sample_id} does not exist")

    self._session.query(models.LibrarySampleLink).filter_by(sample_id=sample_id).delete()
    self._session.delete(sample)
    if commit:
        self._session.commit()

    if not persist_session:
        self.close_session()


def query_samples(
    self, word: str,
    user_id: Optional[int] = None,  # TODO: query from only user owned samples
    limit: Optional[int] = 20
) -> list[SearchResult]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    query = self._session.query(models.Sample).where(
        models.Sample.name.contains(word)
    )

    if limit is not None:
        query = query.limit(limit)

    res = query.all()
    res = [sample.to_search_result() for sample in res]

    if not persist_session:
        self.close_session()

    return res

# This excludes samples already existing in the library


def query_samples_for_library(
    self, word: str,
    exclude_library_id: int,
    user_id: Optional[int] = None,
    limit: Optional[int] = 20
) -> list[SearchResult]:

    persist_session = self._session is not None
    if not self._session:
        self.open_session()

    if self._session.get(models.Library, exclude_library_id) is None:
        raise exceptions.ElementDoesNotExist(f"Library with id {exclude_library_id} does not exist")
    
    params: dict[str, str | int] = {"word": word}

    if exclude_library_id is not None:
        params["library_id"] = exclude_library_id

    q = """
SELECT
    sample.id, sample.name, project.name as project_name, librarysamplelink.library_id,
    similarity(lower(sample.name), lower(%(word)s)) as sml
FROM
    sample
JOIN
    project
ON
    sample.project_id = project.id
LEFT JOIN
    librarysamplelink
ON
    sample.id = librarysamplelink.sample_id
"""
    if exclude_library_id is not None:
        q += """
AND
    librarysamplelink.library_id = %(library_id)s"""

    if user_id is not None:
        params["user_id"] = user_id
        q += """
WHERE
    sample.owner_id = %(user_id)s"""

        if exclude_library_id is not None:
            q += """
AND
    (
    librarysamplelink.library_id != %(library_id)s
        OR
    librarysamplelink.library_id IS NULL
    )"""
    
    else:
        if exclude_library_id is not None:
            q += """
WHERE
    librarysamplelink.library_id != %(library_id)s
        OR
    librarysamplelink.library_id IS NULL"""

    q += """
ORDER BY sml DESC"""

    if limit is not None:
        params["limit"] = limit
        q += """
LIMIT %(limit)s;"""

    else:
        q += ";"

    res = pd.read_sql(q, self._engine, params=params)

    if not persist_session:
        self.close_session()

    res = [
        SearchResult(
            value=sample["id"],
            name=sample["name"],
            description=sample["project_name"]
        ) for _, sample in res.iterrows()
    ]

    return res
