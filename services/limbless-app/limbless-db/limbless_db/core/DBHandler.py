from typing import Optional

from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import orm


class DBHandler():
    def __init__(self, url: str):
        self.url = url
        self._engine = create_engine(self.url)
        self._session: Optional[orm.Session] = None

    def create_tables(self) -> None:
        SQLModel.metadata.create_all(self._engine)

    def open_session(self) -> None:
        if self._session is None:
            self._session = Session(self._engine, expire_on_commit=False)

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    from .model_handlers._sequencer_methods import (
        create_sequencer, get_sequencer, get_sequencers,
        get_num_sequencers, delete_sequencer, get_sequencer_by_name,
        update_sequencer, query_sequencers
    )

    from .model_handlers._project_methods import (
        create_project, get_project, get_projects,
        update_project, delete_project,
        get_num_projects, project_contains_sample_with_name,
        query_projects
    )

    from .model_handlers._experiment_methods import (
        create_experiment, get_experiment, get_experiments,
        update_experiment, delete_experiment,
        get_num_experiments, add_file_to_experiment, remove_file_from_experiment,
    )

    from .model_handlers._sample_methods import (
        create_sample, get_sample, get_samples,
        delete_sample, update_sample,
        query_samples
    )

    from .model_handlers._pool_methods import (
        create_pool, get_pool, get_pools,
        delete_pool, update_pool
    )

    from .model_handlers._library_methods import (
        get_libraries, get_library, create_library,
        update_library, query_libraries, delete_library,
        link_library_pool
    )

    from .model_handlers._user_methods import (
        create_user, get_user, get_users,
        delete_user, update_user,
        get_user_by_email, get_num_users,
        query_users, query_users_by_email,
    )

    from .model_handlers._organism_methods import (
        create_organism, get_organism, get_organisms,
        get_organisms_by_name, query_organisms,
        get_num_organisms
    )

    from .model_handlers._barcode_methods import (
        create_barcode, get_num_seqbarcodes, get_seqbarcodes,
        update_barcode, reverse_complement,
    )

    from .model_handlers._index_kit_methods import (
        create_index_kit, get_index_kit, get_index_kits,
        get_index_kit_by_name, query_index_kit
    )

    from .model_handlers._seq_request_methods import (
        create_seq_request, get_seq_request, get_num_seq_requests,
        get_seq_requests, delete_seq_request, update_seq_request,
        query_seq_requests, submit_seq_request, add_file_to_seq_request
    )

    from .model_handlers._contact_methods import (
        create_contact, update_contact
    )

    from .model_handlers._adapter_methods import (
        create_adapter, get_adapter, get_adapters,
        get_adapter_from_index_kit
    )

    from .model_handlers._cmo_methods import (
        create_cmo, get_cmo, get_cmos,
    )

    from .model_handlers._feature_methods import (
        create_feature, get_feature, get_features,
        delete_feature, update_feature, get_feature_from_kit_by_feature_name,
    )

    from .model_handlers._feature_kit_methods import (
        create_feature_kit, get_feature_kit, get_feature_kits,
        get_feature_kit_by_name, update_feature_kit, delete_feature_kit,
        query_feature_kits
    )

    from .model_handlers._link_methods import (
        get_lanes_in_experiment,
        get_sample_library_links,
        get_available_pools_for_experiment,

        link_experiment_pool,
        link_sample_library,
        link_experiment_seq_request,

        is_sample_in_seq_request,

        unlink_experiment_pool,
        unlink_experiment_seq_request,
    )

    from .model_handlers._file_methods import (
        create_file, get_file, get_files,
    )

    from .pd_handler import (
        get_experiment_libraries_df
    )
