from typing import Optional

from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import orm
from sqlalchemy_utils import database_exists, create_database

from .. import models, categories, logger


class DBHandler():
    def __init__(self, url: str):
        self.url = url
        # self._engine = create_engine(f"sqlite:///{self.url}?check_same_thread=False")
        if not database_exists(self.url):
            logger.debug(f"Created database {self.url}")
            create_database(self.url)
        self._engine = create_engine(self.url)
        self._session: Optional[orm.Session] = None

        SQLModel.metadata.create_all(self._engine)

    def open_session(self) -> None:
        if self._session is None:
            self._session = Session(self._engine, expire_on_commit=False)

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    from .model_handlers._auth_methods import (
        get_user_project_access, get_user_experiment_access,
        get_user_library_access, get_user_sample_access
    )

    from .model_handlers._sequencer_methods import (
        create_sequencer, get_sequencer, get_sequencers,
        get_num_sequencers, delete_sequencer, get_sequencer_by_name,
        update_sequencer, query_sequencers
    )

    from .model_handlers._project_methods import (
        create_project, get_project, get_projects,
        update_project, delete_project,
        get_num_projects, project_contains_sample_with_name
    )

    from .model_handlers._experiment_methods import (
        create_experiment, get_experiment, get_experiments,
        update_experiment, delete_experiment, get_experiment_by_name,
        get_num_experiments
    )

    from .model_handlers._sample_methods import (
        create_sample, get_sample, get_samples,
        delete_sample, update_sample, get_user_sample_by_name,
        get_num_samples, query_samples, query_samples_for_library
    )

    from .model_handlers._run_methods import (
        create_run, get_run, get_runs,
        update_run, delete_run,
        get_run_num_samples,
        get_num_runs
    )

    from .model_handlers._library_methods import (
        create_library, get_library, get_libraries,
        delete_library, update_library,
        get_num_libraries, query_libraries,
        create_library_type
    )

    from .model_handlers._user_methods import (
        create_user, get_user, get_users,
        delete_user, update_user,
        get_user_by_email, get_num_users
    )

    from .model_handlers._organism_methods import (
        create_organism, get_organism, get_organisms,
        get_organisms_by_name, query_organisms,
        get_num_organisms
    )

    from .model_handlers._seq_index_methods import (
        create_seq_index, get_seqindex,
        get_num_seqindices, get_seqindices
    )

    from .model_handlers._index_kit_methods import (
        create_index_kit, get_index_kit, get_index_kits,
        get_index_kit_by_name, query_index_kit,
        get_num_index_kits
    )

    from .model_handlers._seq_request_methods import (
        create_seq_request, get_seq_request, get_num_seq_requests,
        get_seq_requests, delete_seq_request, update_seq_request
    )

    from .model_handlers._contact_methods import (
        create_contact
    )

    from .model_handlers._seq_adapter_methods import (
        create_seq_adapter, get_adapter, get_adapters,
        get_adapter_by_name, query_adapters, get_num_adapters
    )

    from .model_handlers._link_methods import (
        get_project_samples,
        get_project_users,
        get_run_libraries,
        get_library_samples,
        get_library_runs,
        get_user_projects,
        get_sample_libraries,
        get_run_data,
        get_experiment_runs,
        get_sample_indices_from_library,

        link_library_sample,
        link_index_kit_library_type,
        link_run_library,
        link_library_seq_request,

        unlink_library_sample,
        unlink_run_library,
        unlink_project_user
    )
