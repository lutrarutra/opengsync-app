from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import sqlalchemy as sa

from ... import categories as C, queries as Q
from . import pd_transforms as T

if TYPE_CHECKING:
    from ..SyncSession import SyncSession


class SyncPandas:
    def __init__(self, session: SyncSession) -> None:
        self._session = session

    def _read_sql(self, query: sa.Select | str) -> pd.DataFrame:
        return pd.read_sql(query, self._session.connection())

    # ------------------------------------------------------------------
    # Experiment
    # ------------------------------------------------------------------

    def get_experiment_libraries(
        self, experiment_id: int,
        include_sample: bool = False, include_index_kit: bool = False,
        include_seq_request: bool = False, collapse_lanes: bool = False,
        include_indices: bool = False, drop_empty_columns: bool = True,
        collapse_indicies: bool = True,
    ) -> pd.DataFrame:
        query = Q.pd.experiment_libraries(
            experiment_id, include_sample=include_sample,
            include_index_kit=include_index_kit, include_seq_request=include_seq_request,
            include_indices=include_indices,
        )
        df = self._read_sql(query)
        return T.experiment_libraries(df, include_indices, collapse_indicies, drop_empty_columns, collapse_lanes)

    def get_flowcell(self, experiment_id: int | str) -> pd.DataFrame:
        return T.flowcell(self._read_sql(Q.pd.flowcell(experiment_id)))

    def get_experiment_barcodes(self, experiment_id: int) -> pd.DataFrame:
        return T.experiment_barcodes(self._read_sql(Q.pd.experiment_barcodes(experiment_id)))

    def get_experiment_pools(self, experiment_id: int) -> pd.DataFrame:
        return T.experiment_pools(self._read_sql(Q.pd.experiment_pools(experiment_id)))

    def get_experiment_lanes(self, experiment_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.experiment_lanes(experiment_id))

    def get_experiment_laned_pools(self, experiment_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.experiment_laned_pools(experiment_id))

    def get_experiment_seq_qualities(self, experiment_id: int) -> pd.DataFrame:
        return T.experiment_seq_qualities(self._read_sql(Q.pd.experiment_seq_qualities(experiment_id)))

    def get_experiment_stats(
        self, experiment_id: int, per_lane: bool = False,
        expand_qc: bool = True, weighted_average: bool = True,
    ) -> pd.DataFrame:
        df = self._read_sql(Q.pd.experiment_stats(experiment_id))
        return T.experiment_stats(df, per_lane, expand_qc, weighted_average)

    # ------------------------------------------------------------------
    # Project
    # ------------------------------------------------------------------

    def get_project_samples(self, project_id: int, with_libraries: bool = False, pivot: bool = True) -> pd.DataFrame:
        df = self._read_sql(Q.pd.project_samples(project_id, with_libraries=with_libraries))
        return T.project_samples(df, pivot)

    def get_project_libraries(self, project_id: int, collapse_lanes: bool = True) -> pd.DataFrame:
        libraries = self._read_sql(Q.pd.project_libraries_libraries(project_id))
        experiment_ids = libraries["experiment_id"].unique().tolist()
        libraries_ids = libraries["library_id"].unique().tolist()
        lanes = self._read_sql(Q.pd.project_libraries_lanes(experiment_ids, libraries_ids))
        return T.project_libraries(libraries, lanes, collapse_lanes)

    def get_project_seq_requests(self, project_id: int) -> pd.DataFrame:
        return T.project_seq_requests(self._read_sql(Q.pd.project_seq_requests(project_id)))

    def get_project_features(self, project_id: int) -> pd.DataFrame:
        return T.project_features(self._read_sql(Q.pd.project_features(project_id)))

    def get_project_crispr_guides(self, project_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.project_crispr_guides(project_id))

    def get_project_latest_request_share_emails(self, project_id: int) -> pd.DataFrame:
        return T.project_latest_request_share_emails(self._read_sql(Q.pd.project_latest_request_share_emails(project_id)))

    # ------------------------------------------------------------------
    # SeqRequest
    # ------------------------------------------------------------------

    def get_seq_requestor(self, seq_request: int) -> pd.DataFrame:
        return T.seq_requestor(self._read_sql(Q.pd.seq_requestor(seq_request)))

    def get_seq_request_libraries(
        self, seq_request_id: int, include_indices: bool = False, collapse_indicies: bool = False,
    ) -> pd.DataFrame:
        df = self._read_sql(Q.pd.seq_request_libraries(seq_request_id, include_indices=include_indices))
        return T.seq_request_libraries(df, include_indices, collapse_indicies)

    def get_seq_request_samples(self, seq_request_id: int) -> pd.DataFrame:
        return T.seq_request_samples(self._read_sql(Q.pd.seq_request_samples(seq_request_id)))

    def get_seq_request_sample_table(self, seq_request_id: int) -> pd.DataFrame:
        return T.seq_request_sample_table(self._read_sql(Q.pd.seq_request_sample_table(seq_request_id)))

    def get_seq_request_features(self, seq_request_id: int) -> pd.DataFrame:
        return T.seq_request_features(self._read_sql(Q.pd.seq_request_features(seq_request_id)))

    def get_seq_request_share_emails(self, seq_request: int) -> pd.DataFrame:
        return T.seq_request_share_emails(self._read_sql(Q.pd.seq_request_share_emails(seq_request)))

    # ------------------------------------------------------------------
    # Pool
    # ------------------------------------------------------------------

    def get_pool_libraries(self, pool_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.pool_libraries(pool_id))

    def get_pool_barcodes(self, pool_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.pool_barcodes(pool_id))

    def get_pool_num_reads_stats(self, experiment_id: int) -> pd.DataFrame:
        sequenced_df = self._read_sql(Q.pd.pool_num_reads_stats_sequenced(experiment_id))
        planned_df = self._read_sql(Q.pd.pool_num_reads_stats_planned(experiment_id))
        return T.pool_num_reads_stats(sequenced_df, planned_df)

    # ------------------------------------------------------------------
    # Library
    # ------------------------------------------------------------------

    def get_library_features(self, library_id: int) -> pd.DataFrame:
        return T.library_features(self._read_sql(Q.pd.library_features(library_id)))

    def get_library_samples(self, library_id: int, expand_attributes: bool = True) -> pd.DataFrame:
        return T.library_samples(self._read_sql(Q.pd.library_samples(library_id)), expand_attributes)

    def get_library_mux_table(self, library_id: int) -> pd.DataFrame:
        return T.expand_mux(self._read_sql(Q.pd.library_mux_table(library_id)))

    def get_library_sample_pool(self, library_id: int, expand_mux: bool = False) -> pd.DataFrame:
        return T.library_sample_pool(self._read_sql(Q.pd.library_sample_pool(library_id)), expand_mux)

    def get_library_stats(
        self, library_id: int, per_lane: bool = False,
        expand_qc: bool = True, weighted_average: bool = True,
    ) -> pd.DataFrame:
        return T.library_stats(self._read_sql(Q.pd.library_stats(library_id)), per_lane, expand_qc, weighted_average)

    def get_library_properties(
        self, project_id: int | None = None, seq_request_id: int | None = None,
        expand_properties: bool = True,
    ) -> pd.DataFrame:
        if project_id is None and seq_request_id is None:
            raise ValueError("At least one of project_id or seq_request_id must be provided.")
        return T.library_properties(
            self._read_sql(Q.pd.library_properties(project_id=project_id, seq_request_id=seq_request_id)),
            expand_properties,
        )

    def get_library_data_qc(self, library_id: int | None = None, expand: bool = True) -> pd.DataFrame:
        return T.library_data_qc(self._read_sql(Q.pd.library_data_qc(library_id)), expand)

    # ------------------------------------------------------------------
    # Plate
    # ------------------------------------------------------------------

    def get_plate(self, plate_id: int) -> pd.DataFrame:
        return self._read_sql(Q.pd.plate(plate_id))

    # ------------------------------------------------------------------
    # Kit / Feature
    # ------------------------------------------------------------------

    def get_index_kit_barcodes(
        self, index_kit_id: int, per_adapter: bool = False, per_index: bool = False,
    ) -> pd.DataFrame:
        if per_index and per_adapter:
            raise ValueError("Cannot set both per_adapter and per_index to True.")

        df = T.index_kit_barcodes(self._read_sql(Q.pd.index_kit_barcodes(index_kit_id)), per_adapter, per_index)

        if per_index:
            index_kit = self._session.get_one(Q.index_kit.select(id=index_kit_id))
            df = T.index_kit_barcodes_per_index(df, index_kit.type)

        return df

    def get_feature_kit_features(self, feature_kit_id: int) -> pd.DataFrame:
        df = self._read_sql(Q.pd.feature_kit_features(feature_kit_id))
        df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")
        return df

    def get_protocol_kits(self, protocol_id: int | None = None) -> pd.DataFrame:
        return self._read_sql(Q.pd.protocol_kits(protocol_id))

    # ------------------------------------------------------------------
    # Lab prep
    # ------------------------------------------------------------------

    def get_lab_prep_libraries(self, lab_prep_id: int) -> pd.DataFrame:
        return T.lab_prep_libraries(self._read_sql(Q.pd.lab_prep_libraries(lab_prep_id)))

    def get_lab_prep_barcodes(self, lab_prep_id: int) -> pd.DataFrame:
        return T.lab_prep_barcodes(self._read_sql(Q.pd.lab_prep_barcodes(lab_prep_id)))

    def get_lab_prep_pooling_table(self, lab_prep_id: int, expand_mux: bool = False) -> pd.DataFrame:
        return T.lab_prep_pooling_table(self._read_sql(Q.pd.lab_prep_pooling_table(lab_prep_id)), expand_mux)

    # ------------------------------------------------------------------
    # Barcode search
    # ------------------------------------------------------------------

    def query_barcode_sequences(self, sequence: str, limit: int = 10) -> pd.DataFrame:
        return T.query_barcode_sequences(self._read_sql(Q.pd.query_barcode_sequences(sequence, limit)), sequence, limit)

    def match_barcodes_to_kit(
        self, sequences: list[str], barcode_type: C.BarcodeType,
        index_type: C.IndexType | None = None,
    ) -> pd.DataFrame:
        unique = list(set(sequences))
        if not unique:
            return pd.DataFrame()
        return self._read_sql(Q.pd.match_barcodes_to_kit(
            unique, len(unique), barcode_type.id,
            index_type_id=index_type.id if index_type is not None else None,
        ))

    # ------------------------------------------------------------------
    # Raw query
    # ------------------------------------------------------------------

    def query(self, query: sa.Select | str) -> pd.DataFrame:
        return self._read_sql(query)
