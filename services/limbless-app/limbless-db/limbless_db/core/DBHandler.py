from datetime import datetime
from typing import Optional, Union

import sqlalchemy as sa
from sqlalchemy import orm

from limbless_db.models.Base import Base


class DBHandler():
    def __init__(self, user: str, password: str, host: str, db: str = "limbless_db", port: Union[str, int] = 5432):
        self._url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        self._engine = sa.create_engine(self._url)

        try:
            self._engine.connect()
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self._url}':\n{e}")
        self._session: Optional[orm.Session] = None

    def timestamp(self) -> datetime:
        return datetime.now()

    def create_tables(self) -> None:
        Base.metadata.create_all(self._engine)

    def open_session(self, autoflush: bool = False) -> None:
        if self._session is None:
            self._session = orm.Session(self._engine, expire_on_commit=False, autoflush=autoflush)

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

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
        remove_comment_from_experiment, query_experiments
    )

    from .model_handlers._sample_methods import (
        create_sample, get_sample, get_samples,
        delete_sample, update_sample,
        query_samples
    )

    from .model_handlers._pool_methods import (
        create_pool, get_pool, get_pools,
        delete_pool, update_pool, query_pools, dilute_pool,
        get_pool_dilution, get_pool_dilutions, get_next_pool_identifier
    )

    from .model_handlers._library_methods import (
        get_libraries, get_library, create_library,
        update_library, query_libraries, delete_library,
        pool_library, set_library_seq_quality, add_library_index
    )

    from .model_handlers._user_methods import (
        create_user, get_user, get_users,
        delete_user, update_user,
        get_user_by_email, get_num_users,
        query_users, query_users_by_email,
    )

    from .model_handlers._index_kit_methods import (
        create_index_kit, get_index_kit, get_index_kits,
        get_index_kit_by_name, query_index_kit
    )

    from .model_handlers._seq_request_methods import (
        create_seq_request, get_seq_request,
        get_seq_requests, delete_seq_request, update_seq_request,
        query_seq_requests, submit_seq_request,
        add_file_to_seq_request, remove_file_from_seq_request,
        remove_comment_from_seq_request, add_seq_request_share_email, remove_seq_request_share_email,
        process_seq_request
    )

    from .model_handlers._contact_methods import (
        create_contact, update_contact
    )

    from .model_handlers._adapter_methods import (
        create_adapter, get_adapter, get_adapters,
        get_adapter_from_index_kit, add_barcode_to_adapter
    )

    from .model_handlers._lane_methods import (
        create_lane, get_lane, get_lanes, update_lane, get_experiment_lane
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

    from .model_handlers._sequencer_methods import (
        create_sequencer, get_sequencer, get_sequencers,
        get_num_sequencers, delete_sequencer, get_sequencer_by_name,
        update_sequencer, query_sequencers
    )

    from .model_handlers._plate_methods import (
        create_plate, get_plate, get_plates,
        delete_plate, add_sample_to_plate, add_library_to_plate, clear_plate,
        get_plate_sample
    )

    from .model_handlers._link_methods import (
        get_sample_library_links,

        add_pool_to_lane,
        remove_pool_from_lane,

        link_feature_library,
        link_sample_library,
        link_pool_experiment,

        is_sample_in_seq_request,

        unlink_feature_library,
        unlink_pool_experiment,
    )

    from .model_handlers._file_methods import (
        create_file, get_file, get_files, file_permissions_check
    )

    from .model_handlers._visium_annotation_methods import (
        create_visium_annotation, get_visium_annotation
    )

    from .model_handlers._comment_methods import (
        create_comment, delete_comment, get_comments, get_comment,
        add_experiment_comment, remove_experiment_comment,
        add_seq_request_comment, remove_seq_request_comment
    )

    from .model_handlers._seq_run_methods import (
        create_seq_run, get_seq_run, get_seq_runs, update_seq_run, query_seq_runs
    )

    from .pd_handler import (
        get_experiment_libraries_df, get_experiment_pools_df,
        get_experiment_lanes_df, get_experiment_laned_pools_df,
        get_pool_libraries_df, get_seq_request_libraries_df,
        get_seq_requestor_df, get_seq_request_share_emails_df,
        get_library_features_df, get_library_cmos_df, get_experiment_seq_qualities_df,
        get_plate_df, get_seq_request_samples_df
    )
