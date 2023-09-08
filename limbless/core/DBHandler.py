from typing import Optional

from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import orm
from sqlalchemy_utils import database_exists, create_database

from .. import models, categories, logger


class DBHandler():
    def __init__(self, url: str, create_admin: bool = True):
        self.url = url
        # self._engine = create_engine(f"sqlite:///{self.url}?check_same_thread=False")
        if not database_exists(self.url):
            logger.debug(f"Created database {self.url}")
            create_database(self.url)
        self._engine = create_engine(self.url)
        self._session: Optional[orm.Session] = None

        SQLModel.metadata.create_all(self._engine)

        if create_admin:
            self.open_session()
            self.__admin = self._session.get(models.User, 1)
            if not self.__admin:
                self.__admin = self.create_user(
                    email="admin@limbless.com", password="password",
                    role=categories.UserRole.ADMIN
                )
            self._session.add(self.__admin)
            self.close_session(commit=True)

    def open_session(self) -> None:
        self._session = Session(self._engine, expire_on_commit=False)

    def close_session(self, commit=True) -> None:
        if commit:
            self._session.commit()
        self._session.close()
        self._session = None

    from .model_handlers._auth_methods import (
        get_user_project_access, get_user_experiment_access,
        get_user_library_access, get_user_sample_access
    )

    from .model_handlers._project_methods import (
        create_project, get_project, get_projects,
        update_project, delete_project, get_project_by_name,
        get_num_projects, project_contains_sample_with_name
    )

    from .model_handlers._experiment_methods import (
        create_experiment, get_experiment, get_experiments,
        update_experiment, delete_experiment, get_experiment_by_name,
        get_num_experiments
    )

    from .model_handlers._sample_methods import (
        create_sample, get_sample, get_samples,
        delete_sample, update_sample, get_sample_by_name,
        get_num_samples, query_samples
    )

    from .model_handlers._run_methods import (
        create_run, get_run, get_runs,
        update_run, delete_run,
        get_run_num_samples,
        get_num_runs
    )

    from .model_handlers._library_methods import (
        create_library, get_library, get_libraries,
        delete_library, update_library, get_library_by_name,
        get_num_libraries
    )

    from .model_handlers._user_methods import (
        create_user, get_user, get_users,
        delete_user, update_user,
        get_user_by_email
    )

    from .model_handlers._organism_methods import (
        create_organism, get_organism, get_organisms,
        get_organisms_by_name, query_organisms,
        get_num_organisms
    )

    from .model_handlers._seqindex_methods import (
        create_seqindex, get_seqindex, get_seqindices_by_adapter,
        get_num_seqindices, query_adapters, get_adapters_from_kit
    )

    from .model_handlers._indexkit_methods import (
        create_indexkit, get_indexkit, get_indexkit_by_name,
        query_indexkit
    )

    from .model_handlers._link_methods import (
        get_project_samples,
        get_project_users,
        get_run_libraries,
        get_library_samples,
        get_library_runs,
        get_user_projects,
        get_user_samples,
        get_sample_libraries,
        get_experiment_data,
        get_run_data,
        get_experiment_runs,

        link_project_user,
        link_library_sample,
        link_run_library,
        link_library_user,

        unlink_library_sample,
        unlink_run_library,
        unlink_project_user
    )
