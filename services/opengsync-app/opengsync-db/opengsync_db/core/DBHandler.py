from datetime import datetime
from typing import Optional, Union

import loguru

import sqlalchemy as sa
from sqlalchemy import orm

from ..models.Base import Base
from .. import models


class DBHandler():
    Session: orm.scoped_session

    def __init__(self, logger: Optional["loguru.Logger"] = None, expire_on_commit: bool = False) -> None:
        self._logger = logger
        self._session: orm.Session | None = None
        self._connection: sa.engine.Connection | None = None
        self.expire_on_commit = expire_on_commit
        self.__needs_commit = False
        
    def connect(
        self, user: str, password: str, host: str, db: str = "opengsync_db", port: Union[str, int] = 5432
    ) -> None:
        self._url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        self.public_url = f"{self._url.split(':')[0]}://{host}:{port}/{db}"
        self._engine = sa.create_engine(self._url)
        try:
            self._connection = self._engine.connect()
        except Exception as e:
            raise Exception(f"Could not connect to DB '{self.public_url}':\n{e}")
        
        self.info(f"Connected to DB '{self.public_url}'")

        self.session_factory = orm.sessionmaker(bind=self._engine, expire_on_commit=self.expire_on_commit)
        DBHandler.Session = orm.scoped_session(self.session_factory)
        from . import listeners  # noqa: F401

    def info(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).info(message)
        else:
            print(f"LOG: {message}")
    
    def error(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).error(message)
        else:
            print(f"ERROR: {message}")

    def warn(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).warning(message)
        else:
            print(f"WARNING: {message}")

    def debug(self, *values: object) -> None:
        message = " ".join([str(value) for value in values])
        if self._logger is not None:
            self._logger.opt(depth=1).debug(message)
        else:
            print(f"DEBUG: {message}")

    @property
    def session(self) -> orm.Session:
        if self._session is None:
            raise Exception("Session is not open.")
        return self._session

    @property
    def connection(self) -> sa.engine.Connection:
        if self._connection is None:
            raise Exception("Connection is not open.")
        return self._connection

    def timestamp(self) -> datetime:
        return datetime.now()
    
    def commit(self) -> None:
        if self._session is not None:
            self._session.commit()
        else:
            raise Exception("Session is not open, cannot commit changes.")

    def flush(self) -> None:
        if self._session is not None:
            self.__needs_commit = True
            self._session.flush()
        else:
            raise Exception("Session is not open, cannot flush changes.")

    def refresh(self, obj: object) -> None:
        if self._session is not None:
            self._session.refresh(obj)
        else:
            raise Exception("Session is not open, cannot refresh session state.")
        
    def create_tables(self) -> None:
        """Create database tables with pg_trgm extension if needed."""
        inspector = sa.inspect(self._engine)
        
        if inspector.has_table(models.User.__tablename__):
            self.warn("Tables already exist, skipping creation...")
            return
        
        try:
            with self._engine.begin() as conn:
                conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                self.info("Created pg_trgm extension")
                
                Base.metadata.create_all(conn)
                self.info("Successfully created all tables")
                
        except Exception as e:
            self.error(f"Failed to create tables: {str(e)}")
            raise RuntimeError("Database initialization failed") from e

    def open_session(self, autoflush: bool = False) -> None:
        self._logger.opt(depth=1).error("Opening database session...")
        if self._session is not None:
            self.warn("Session is already open")
            return
        self._session = DBHandler.Session(autoflush=autoflush)

    def close_session(self, commit: bool = True, rollback: bool = False) -> None:
        if self._session is None:
            self.warn("Session is already closed or was never opened.")
            return
       
        if commit and not rollback:
            if self.__needs_commit or self.session.dirty or self.session.new or self.session.deleted:
                try:
                    self.session.commit()
                except Exception:
                    self.error("Commit failed: - rolling back transaction.")
                    self.session.rollback()
                    raise
        elif rollback:
            self.info("Rolling back transaction...")
            self.session.rollback()
        else:
            if not commit and self.__needs_commit:
                self.warn("Session was not committed, but changes were made. This may lead to data loss.")

        self._session = DBHandler.Session.remove()

    def rollback(self) -> None:
        if self._session is None:
            self.error("Session is not open, cannot rollback.")
            raise Exception("Session is not open, cannot rollback.")
        self.info("Rolling back transaction...")
        self._session.rollback()

    def close_connection(self) -> None:
        if self._connection is not None:
            self._connection = self._connection.close()
            self.info("Connection closed.")

    def __del__(self):
        if self._session is not None:
            self.close_session()
        self.close_connection()
        self._engine.dispose()

    from .model_handlers._project_methods import (
        create_project, get_project, get_projects,
        update_project, delete_project,
        query_projects
    )

    from .model_handlers._experiment_methods import (
        create_experiment, get_experiment, get_experiments,
        update_experiment, delete_experiment,
        get_num_experiments, query_experiments
    )

    from .model_handlers._sample_methods import (
        create_sample, get_sample, get_samples,
        delete_sample, update_sample, query_samples,
        set_sample_attribute, get_sample_attribute,
        get_user_sample_access_type, delete_sample_attribute
    )

    from .model_handlers._pool_methods import (
        create_pool, get_pool, get_pools,
        delete_pool, update_pool, query_pools, dilute_pool,
        get_pool_dilution, get_pool_dilutions, get_user_pool_access_type,
        clone_pool, get_number_of_cloned_pools, merge_pools
    )

    from .model_handlers._library_methods import (
        get_libraries, get_library, create_library,
        update_library, query_libraries, delete_library,
        add_library_to_pool, set_library_seq_quality, add_library_index,
        remove_library_indices, get_user_library_access_type, clone_library,
        get_number_of_cloned_libraries
    )

    from .model_handlers._user_methods import (
        create_user, get_user, get_users,
        delete_user, update_user,
        get_user_by_email, get_num_users,
        query_users, query_users_by_email,
        get_user_affiliations
    )

    from .model_handlers._index_kit_methods import (
        create_index_kit, get_index_kit, get_index_kits,
        get_index_kit_by_name, update_index_kit,
        remove_all_barcodes_from_kit, get_index_kit_by_identifier,
        query_index_kits
    )

    from .model_handlers._seq_request_methods import (
        create_seq_request, get_seq_request,
        get_seq_requests, delete_seq_request, update_seq_request,
        query_seq_requests, submit_seq_request,
        add_seq_request_share_email, remove_seq_request_share_email,
        process_seq_request, get_user_seq_request_access_type, clone_seq_request
    )

    from .model_handlers._contact_methods import (
        create_contact, update_contact
    )

    from .model_handlers._lane_methods import (
        create_lane, get_lane, get_lanes, update_lane, get_experiment_lane,
        delete_lane
    )

    from .model_handlers._feature_methods import (
        create_feature, get_feature, get_features,
        delete_feature, update_feature, get_features_from_kit_by_feature_name,
        delete_orphan_features
    )

    from .model_handlers._feature_kit_methods import (
        create_feature_kit, get_feature_kit, get_feature_kits,
        get_feature_kit_by_name, update_feature_kit,
        remove_all_features_from_kit
    )

    from .model_handlers._sequencer_methods import (
        create_sequencer, get_sequencer, get_sequencers,
        get_num_sequencers, delete_sequencer, get_sequencer_by_name,
        update_sequencer, query_sequencers
    )

    from .model_handlers._adapter_methods import (
        create_adapter, get_adapter, get_adapters
    )

    from .model_handlers._plate_methods import (
        create_plate, get_plate, get_plates,
        delete_plate, add_sample_to_plate, add_library_to_plate, clear_plate,
        get_plate_sample
    )

    from .model_handlers._barcode_methods import (
        create_barcode, get_barcode, get_barcodes, query_barcode_sequences
    )

    from .model_handlers._lab_prep_methods import (
        create_lab_prep, get_lab_prep, get_lab_preps, get_next_protocol_number,
        update_lab_prep, add_library_to_prep, remove_library_from_prep, query_lab_preps,
        delete_lab_prep
    )

    from .model_handlers._kit_methods import (
        create_kit, get_kit, get_kits, query_kits, get_kit_by_name, delete_kit,
        update_kit
    )

    from .model_handlers._link_methods import (
        get_sample_library_link,
        get_sample_library_links,
        get_laned_pool_link,
        update_sample_library_link,

        add_pool_to_lane,
        remove_pool_from_lane,

        update_laned_pool_link,

        link_features_library,
        link_feature_library,
        link_sample_library,
        link_pool_experiment,

        is_sample_in_seq_request,

        unlink_sample_library,
        unlink_feature_library,
        unlink_pool_experiment,
    )

    from .model_handlers._file_methods import (
        create_file, get_file, get_files, file_permissions_check, delete_file
    )

    from .model_handlers._comment_methods import (
        create_comment, delete_comment, get_comments, get_comment,
    )

    from .model_handlers._seq_run_methods import (
        create_seq_run, get_seq_run, get_seq_runs, update_seq_run, query_seq_runs
    )

    from .model_handlers._event_methods import (
        create_event, get_event, get_events, update_event, delete_event
    )

    from .model_handlers._group_methods import (
        create_group, get_group, get_groups, update_group,
        query_groups, add_user_to_group, remove_user_from_group,
        get_group_user_affiliation, get_group_affiliations,
        get_group_by_name
    )

    from .pd_handler import (
        get_experiment_libraries_df, get_experiment_pools_df,
        get_experiment_lanes_df, get_experiment_laned_pools_df,
        get_pool_libraries_df, get_seq_request_libraries_df,
        get_seq_requestor_df, get_seq_request_share_emails_df,
        get_library_features_df, get_library_samples_df, get_experiment_seq_qualities_df,
        get_plate_df, get_seq_request_samples_df, get_index_kit_barcodes_df,
        get_experiment_barcodes_df, get_feature_kit_features_df, get_seq_request_features_df,
        get_project_samples_df, get_lab_prep_libraries_df,
        get_lab_prep_samples_df, query_barcode_sequences_df, get_flowcell_df,
        get_library_mux_table_df, get_project_libraries_df,
    )

    from .model_handlers._share_methods import (
        create_share_token, get_share_tokens, get_share_token
    )
