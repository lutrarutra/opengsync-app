import pandas as pd

import sqlalchemy as sa

from ... import models, categories as C, queries as Q
from ..DBBlueprint import DBBlueprint


class PandasBP(DBBlueprint):
    @DBBlueprint.transaction
    def get_experiment_libraries(
        self, experiment_id: int,
        include_sample: bool = False, include_index_kit: bool = False,
        include_seq_request: bool = False, collapse_lanes: bool = False,
        include_indices: bool = False, drop_empty_columns: bool = True,
        collapse_indicies: bool = True
    ) -> pd.DataFrame:
        query = Q.pd.experiment_libraries(
            experiment_id,
            include_sample=include_sample,
            include_index_kit=include_index_kit,
            include_seq_request=include_seq_request,
            include_indices=include_indices,
        )

        df = pd.read_sql(query, self.db.session.connection())

        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["reference"] = C.GenomeRef.map_series(df["reference_id"], na_action="ignore")
        df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

        order = [
            "lane", "library_id", "sample_name", "library_name", "library_type", "reference", "pool_name",
            "pool_id", "library_type_id", "reference_id",
        ]
        order += [c for c in df.columns if c not in order]

        df = df[order]

        if include_indices and collapse_indicies:
            df = df.groupby(df.columns.difference(["sequence_i7", "sequence_i5", "name_i7", "name_i5"]).tolist(), as_index=False).agg({"sequence_i7": list, "sequence_i5": list, "name_i7": list, "name_i5": list}).copy().rename(
                columns={
                    "sequence_i7": "sequences_i7", "sequence_i5": "sequences_i5",
                    "name_i7": "names_i7", "name_i5": "names_i5"
                }
            )
        
        if drop_empty_columns:
            df = df.dropna(axis="columns", how="all")
        
        if collapse_lanes:
            df = df.groupby(df.columns.difference(['lane']).tolist(), as_index=False).agg({'lane': list}).rename(columns={'lane': 'lanes'})
            order[0] = "lanes"
            df = df[[c for c in order if c in df.columns]]
        
        return df

    @DBBlueprint.transaction
    def get_flowcell(self, experiment_id: int | str) -> pd.DataFrame:
        query = Q.pd.flowcell(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())

        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["reference"] = C.GenomeRef.map_series(df["reference_id"], na_action="ignore")
        df["orientation"] = C.BarcodeOrientation.map_series(df["orientation_id"], na_action="ignore")

        df = df[["lane", "sample_name", "library_name", "library_type", "reference", "seq_request_id", "sequence_i7", "sequence_i5", "orientation", "read_structure", "protocol_name", "pool_name", "library_id"]]

        return df

    @DBBlueprint.transaction
    def get_experiment_barcodes(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.experiment_barcodes(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["orientation"] = C.BarcodeOrientation.map_series(df["orientation_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_experiment_pools(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.experiment_pools(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["status"] = C.PoolStatus.map_series(df["status_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_plate(self, plate_id: int) -> pd.DataFrame:
        query = Q.pd.plate(plate_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_experiment_lanes(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.experiment_lanes(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_experiment_laned_pools(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.experiment_laned_pools(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_pool_libraries(self, pool_id: int) -> pd.DataFrame:
        query = Q.pd.pool_libraries(pool_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_pool_barcodes(self, pool_id: int) -> pd.DataFrame:
        query = Q.pd.pool_barcodes(pool_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_seq_requestor(self, seq_request: int) -> pd.DataFrame:
        query = Q.pd.seq_requestor(seq_request)
        df = pd.read_sql(query, self.db.session.connection())
        df["role"] = C.UserRole.map_series(df["role_id"], na_action="ignore")
        return df

    @DBBlueprint.transaction
    def get_library_features(self, library_id: int) -> pd.DataFrame:
        query = Q.pd.library_features(library_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["feature_type"] = C.FeatureType.map_series(df["feature_type_id"], na_action="ignore")
        return df

    @DBBlueprint.transaction
    def get_library_samples(self, library_id: int, expand_attributes: bool = True) -> pd.DataFrame:
        query = Q.pd.library_samples(library_id)
        df = pd.read_sql(query, self.db.session.connection())
        if expand_attributes:
            expanded = df["attributes"].apply(pd.Series)
            for col in expanded.columns:
                expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

            df = pd.concat([df.drop(columns=["attributes"]), expanded], axis=1)
        return df

    @DBBlueprint.transaction
    def get_library_mux_table(self, library_id: int) -> pd.DataFrame:
        query = Q.pd.library_mux_table(library_id)
        df = pd.read_sql(query, self.db.session.connection())

        expanded = df["mux"].apply(pd.Series)
        for col in expanded.columns:
            expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

        return df
    
    @DBBlueprint.transaction
    def get_project_crispr_guides(self, project_id: int) -> pd.DataFrame:
        query = Q.pd.project_crispr_guides(project_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df

    @DBBlueprint.transaction
    def get_seq_request_libraries(
        self, seq_request_id: int, include_indices: bool = False,
        collapse_indicies: bool = False
    ) -> pd.DataFrame:
        query = Q.pd.seq_request_libraries(seq_request_id, include_indices=include_indices)
        df = pd.read_sql(query, self.db.session.connection())

        if include_indices and collapse_indicies:
            df = df.groupby(df.columns.difference(["sequence_i7", "sequence_i5", "name_i7", "name_i5"]).tolist(), as_index=False).agg({"sequence_i7": list, "sequence_i5": list, "name_i7": list, "name_i5": list}).copy().rename(
                columns={
                    "sequence_i7": "sequences_i7", "sequence_i5": "sequences_i5",
                    "name_i7": "names_i7", "name_i5": "names_i5"
                }
            )

        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_seq_request_samples(
        self, seq_request_id: int
    ) -> pd.DataFrame:
        query = Q.pd.seq_request_samples(seq_request_id)
        df = pd.read_sql(query, self.db.session.connection())

        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")
        df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

        return df
    
    @DBBlueprint.transaction
    def get_seq_request_sample_table(
        self, seq_request_id: int
    ) -> pd.DataFrame:
        query = Q.pd.seq_request_sample_table(seq_request_id)
        df = pd.read_sql(query, self.db.session.connection())

        if not df.empty:
            expanded = df["attributes"].apply(pd.Series)
            for col in expanded.columns:
                expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

            df = pd.concat([df.drop(columns=["attributes"]), expanded], axis=1)

        return df

    @DBBlueprint.transaction
    def get_experiment_seq_qualities(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.experiment_seq_qualities(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())

        df.loc[df["library_id"].isna(), "library_name"] = "Undetermined"
        df["library_id"] = df["library_id"].astype(pd.Int64Dtype())

        return df

    @DBBlueprint.transaction
    def get_index_kit_barcodes(self, index_kit_id: int, per_adapter: bool = False, per_index: bool = False) -> pd.DataFrame:
        if per_index and per_adapter:
            raise ValueError("Cannot set both per_adapter and per_index to True.")
        
        query = Q.pd.index_kit_barcodes(index_kit_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["name"] = df["name"].astype(str)
        df["well"] = df["well"].astype(str)
        df["type"] = C.BarcodeType.map_series(df["type_id"], na_action="ignore")

        if per_adapter or per_index:
            df = df.groupby(
                df.columns.difference(["id", "sequence", "name", "type_id", "type"]).tolist(), as_index=False, dropna=False
            ).agg(
                {"id": list, "sequence": list, "name": list, "type_id": list, "type": list}
            ).rename(
                columns={"id": "ids", "sequence": "sequences", "name": "names", "type_id": "type_ids", "type": "types"}
            )

        if per_index:
            index_kit = self.db.session.get_one(Q.index_kit.select(id=index_kit_id))
            
            if index_kit.type == C.IndexType.TENX_ATAC_INDEX:
                barcode_data = {
                    "well": [],
                    "adapter_id": [],
                    "name": [],
                    "sequence_1": [],
                    "sequence_2": [],
                    "sequence_3": [],
                    "sequence_4": [],
                }
                for _, row in df.iterrows():
                    barcode_data["well"].append(row["well"])
                    barcode_data["name"].append(row["names"][0])
                    barcode_data["adapter_id"].append(row["adapter_id"])
                    for i in range(4):
                        barcode_data[f"sequence_{i + 1}"].append(row["sequences"][i])
            elif index_kit.type == C.IndexType.DUAL_INDEX:
                barcode_data = {
                    "well": [],
                    "adapter_id": [],
                    "name_i7": [],
                    "sequence_i7": [],
                    "name_i5": [],
                    "sequence_i5": [],
                }
                for _, row in df.iterrows():
                    barcode_data["well"].append(row["well"])
                    barcode_data["adapter_id"].append(row["adapter_id"])
                    for i in range(2):
                        if row["types"][i] == C.BarcodeType.INDEX_I7:
                            barcode_data["name_i7"].append(row["names"][i])
                            barcode_data["sequence_i7"].append(row["sequences"][i])
                        else:
                            barcode_data["name_i5"].append(row["names"][i])
                            barcode_data["sequence_i5"].append(row["sequences"][i])
            elif index_kit.type == C.IndexType.COMBINATORIAL_DUAL_INDEX:
                barcode_data = {
                    "adapter_id": [],
                    "name_i7": [],
                    "sequence_i7": [],
                    "name_i5": [],
                    "sequence_i5": [],
                }
                for _, row in df.iterrows():
                    barcode_data["adapter_id"].append(row["adapter_id"])

                    if row["types"][0] == C.BarcodeType.INDEX_I7:
                        barcode_data["name_i7"].append(row["names"][0])
                        barcode_data["sequence_i7"].append(row["sequences"][0])
                        barcode_data["name_i5"].append(None)
                        barcode_data["sequence_i5"].append(None)
                    else:
                        barcode_data["name_i7"].append(None)
                        barcode_data["sequence_i7"].append(None)
                        barcode_data["name_i5"].append(row["names"][0])
                        barcode_data["sequence_i5"].append(row["sequences"][0])

            elif index_kit.type == C.IndexType.SINGLE_INDEX_I7:
                barcode_data = {
                    "well": [],
                    "adapter_id": [],
                    "name_i7": [],
                    "sequence_i7": [],
                }
                for _, row in df.iterrows():
                    barcode_data["adapter_id"].append(row["adapter_id"])
                    barcode_data["well"].append(row["well"])
                    barcode_data["name_i7"].append(row["names"][0])
                    barcode_data["sequence_i7"].append(row["sequences"][0])
            else:
                raise ValueError(f"Unsupported index kit type: {index_kit.type}")

            df = pd.DataFrame(barcode_data)

        return df

    def get_feature_kit_features(self, feature_kit_id: int) -> pd.DataFrame:
        query = Q.pd.feature_kit_features(feature_kit_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_seq_request_features(self, seq_request_id: int) -> pd.DataFrame:
        query = Q.pd.seq_request_features(seq_request_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_project_features(self, project_id: int) -> pd.DataFrame:
        query = Q.pd.project_features(project_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_project_samples(self, project_id: int, with_libraries: bool = False, pivot: bool = True) -> pd.DataFrame:
        query = Q.pd.project_samples(project_id, with_libraries=with_libraries)
        df = pd.read_sql(query, self.db.session.connection())

        if not df.empty and pivot:
            expanded = df["attributes"].apply(pd.Series)
            for col in expanded.columns:
                expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

            df = pd.concat([df.drop(columns=["attributes"]), expanded], axis=1)
        return df
    
    @DBBlueprint.transaction
    def get_project_seq_requests(self, project_id: int) -> pd.DataFrame:
        query = Q.pd.project_seq_requests(project_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["status"] = C.SeqRequestStatus.map_series(df["status_id"], na_action="ignore")
        return df

    @DBBlueprint.transaction
    def get_project_libraries(self, project_id: int, collapse_lanes: bool = True) -> pd.DataFrame:
        query = Q.pd.project_libraries_libraries(project_id)
        libraries = pd.read_sql(query, self.db.session.connection())
        experiment_ids = libraries["experiment_id"].unique().tolist()
        libraries_ids = libraries["library_id"].unique().tolist()

        libraries["mux_type"] = C.MUXType.map_series(libraries["mux_type_id"], na_action="ignore")
        libraries["genome_ref"] = C.GenomeRef.map_series(libraries["genome_ref_id"], na_action="ignore")
        libraries["library_type"] = C.LibraryType.map_series(libraries["library_type_id"], na_action="ignore")

        lanes_query = Q.pd.project_libraries_lanes(experiment_ids, libraries_ids)
        lanes = pd.read_sql(lanes_query, self.db.session.connection())
        if collapse_lanes:
            order = [
                "sample_name", "library_name", "sample_pool",
                "library_type", "genome_ref", "experiment_name", "lanes",
                "mux", "mux_type", "properties", "library_id", "sample_id", "seq_request_id"
            ]
            lanes = lanes.sort_values("lane").groupby(
                lanes.columns.difference(["lane"]).tolist(), as_index=False, dropna=False,
            ).agg({"lane": list}).rename(columns={"lane": "lanes"})
        else:
            order = [
                "sample_name", "library_name", "sample_pool",
                "library_type", "genome_ref", "experiment_name", "lane",
                "mux", "mux_type", "properties", "library_id", "sample_id", "seq_request_id"
            ]

        merged = pd.merge(libraries, lanes, on=["library_id", "experiment_id"], how="left")
        return merged[order].copy()

    @DBBlueprint.transaction
    def get_lab_prep_libraries(self, lab_prep_id: int) -> pd.DataFrame:
        query = Q.pd.lab_prep_libraries(lab_prep_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["status"] = C.LibraryStatus.map_series(df["status_id"], na_action="ignore")
        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")
        df["index_type"] = C.IndexType.map_series(df["index_type_id"], na_action="ignore")
        return df
    
    @DBBlueprint.transaction
    def get_lab_prep_barcodes(self, lab_prep_id: int) -> pd.DataFrame:
        query = Q.pd.lab_prep_barcodes(lab_prep_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["index_type"] = C.IndexType.map_series(df["index_type_id"], na_action="ignore")

        return df

    @DBBlueprint.transaction
    def get_lab_prep_pooling_table(self, lab_prep_id: int, expand_mux: bool = False) -> pd.DataFrame:
        query = Q.pd.lab_prep_pooling_table(lab_prep_id)
        df = pd.read_sql(query, self.db.session.connection()).sort_values(["library_id", "sample_id"])
        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

        if expand_mux and not df.empty:
            expanded = df["mux"].apply(pd.Series)
            for col in expanded.columns:
                expanded[f"mux_{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

            df = pd.concat([df, expanded], axis=1)
            
        return df

    @DBBlueprint.transaction
    def query_barcode_sequences(self, sequence: str, limit: int = 10) -> pd.DataFrame:
        query = Q.pd.query_barcode_sequences(sequence, limit)
        df = pd.read_sql(query, self.db.session.connection())
        
        def hamming_distance(str1: str, str2: str) -> int:
            min_length = min(len(str1), len(str2))
            distance = sum(c1 != c2 for c1, c2 in zip(str1[:min_length], str2[:min_length]))
            distance += abs(len(str1) - len(str2))
            return distance

        df["hamming"] = df["sequence"].apply(lambda x: hamming_distance(x, sequence))
        df["type"] = C.BarcodeType.map_series(df["type_id"], na_action="ignore")

        return df
    
    @DBBlueprint.transaction
    def get_library_sample_pool(self, library_id: int, expand_mux: bool = False) -> pd.DataFrame:
        query = Q.pd.library_sample_pool(library_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
        df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

        if expand_mux and not df.empty:
            expanded = df["mux"].apply(pd.Series)
            for col in expanded.columns:
                expanded[f"mux_{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

            df = pd.concat([df, expanded], axis=1)

        return df
    
    @DBBlueprint.transaction
    def get_protocol_kits(self, protocol_id: int | None = None) -> pd.DataFrame:
        query = Q.pd.protocol_kits(protocol_id)
        df = pd.read_sql(query, self.db.session.connection())
        return df
    
    @DBBlueprint.transaction
    def get_library_stats(self, library_id: int, per_lane: bool = False, expand_qc: bool = True, weighted_average: bool = True) -> pd.DataFrame:
        query = Q.pd.library_stats(library_id)
        df = pd.read_sql(query, self.db.session.connection())

        if expand_qc and not df.empty:
            expanded = df["qc"].apply(pd.Series)
            for col in expanded.columns:
                expanded[f"{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

            df = pd.concat([df, expanded], axis=1)
            df = df.drop(columns=["qc"])

        if not per_lane:
            df = df.drop(columns=["lane"])
            df["weight"] = df["num_reads"] / df["num_reads"].sum()
            agg_dict = { "num_reads": "sum" }
            if weighted_average:
                agg_dict |= {col: lambda x: (x * df.loc[x.index, "weight"]).sum() if pd.api.types.is_numeric_dtype(x) else x.iloc[0] for col in df.columns if col not in ["num_reads", "weight"]}
            else:
                agg_dict |= {col: "mean" if pd.api.types.is_numeric_dtype(df[col]) else "first" for col in df.columns if col not in ["num_reads", "weight"]}
 
            df["dummy"] = 0  # to allow groupby
            df = df.groupby(["dummy"], as_index=False).agg(agg_dict)
            df = df.drop(columns=["dummy"])

        return df
    
    @DBBlueprint.transaction
    def get_experiment_stats(self, experiment_id: int, per_lane: bool = False, expand_qc: bool = True, weighted_average: bool = True) -> pd.DataFrame:
        query = Q.pd.experiment_stats(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["library_id"] = df["library_id"].astype(pd.Int64Dtype())

        if expand_qc and not df.empty:
            expanded = df["qc"].apply(pd.Series)
            for col in expanded.columns:
                expanded[f"{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

            df = pd.concat([df, expanded], axis=1)
            df = df.drop(columns=["qc"])

        if not per_lane:
            df = df.drop(columns=["lane"])
            # weights by library
            df["weight"] = df["num_reads"] / df.groupby(["library_id", "library_name"], dropna=False)["num_reads"].transform("sum")
            agg_dict = { "num_reads": "sum" }
            if weighted_average:
                agg_dict |= {col: lambda x: (x * df.loc[x.index, "weight"]).sum() if pd.api.types.is_numeric_dtype(x) else x.iloc[0] for col in df.columns if col not in ["num_reads", "weight", "library_id", "library_name"]}
            else:
                agg_dict |= {col: "mean" if pd.api.types.is_numeric_dtype(df[col]) else "first" for col in df.columns if col not in ["num_reads", "weight", "library_id", "library_name"]}

            df = df.groupby(["library_id", "library_name"], as_index=False, dropna=False).agg(agg_dict)

        return df
    
    @DBBlueprint.transaction
    def get_seq_request_share_emails(self, seq_request: int) -> pd.DataFrame:
        query = Q.pd.seq_request_share_emails(seq_request)
        df = pd.read_sql(query, self.db.session.connection())
        df["status"] = C.DeliveryStatus.map_series(df["status_id"], na_action="ignore")

        return df
    
    @DBBlueprint.transaction
    def get_project_latest_request_share_emails(self, project_id: int) -> pd.DataFrame:
        query = Q.pd.project_latest_request_share_emails(project_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["status"] = C.DeliveryStatus.map_series(df["status_id"], na_action="ignore")
        return df
    
    @DBBlueprint.transaction
    def get_pool_num_reads_stats(self, experiment_id: int) -> pd.DataFrame:
        query = Q.pd.pool_num_reads_stats_sequenced(experiment_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["pool_id"] = df["pool_id"].astype(pd.Int64Dtype())

        stats = df.groupby(
            ["pool_id", "pool_name"], dropna=False
        ).agg(
            num_reads=pd.NamedAgg(column="num_reads", aggfunc="sum"),
            num_m_reads_requested=pd.NamedAgg(column="num_m_reads_requested", aggfunc="first"),
        ).reset_index()

        planned_query = Q.pd.pool_num_reads_stats_planned(experiment_id)
        planned_reads_df = pd.read_sql(planned_query, self.db.session.connection())
        planned_reads_df["pool_id"] = planned_reads_df["pool_id"].astype(pd.Int64Dtype())
        planned_reads = planned_reads_df.groupby(
            ["pool_id"], dropna=False
        ).agg(
            num_m_reads_planned=pd.NamedAgg(column="num_m_reads", aggfunc="sum"),
        ).reset_index()
        stats = pd.merge(
            stats, planned_reads, on="pool_id", how="left"
        )
        
        stats["num_reads_requested"] = None
        stats.loc[stats["num_m_reads_requested"].notna(), "num_reads_requested"] = stats["num_m_reads_requested"] * 1_000_000


        stats["num_planned_reads"] = None
        stats.loc[stats["num_m_reads_planned"].notna(), "num_planned_reads"] = stats["num_m_reads_planned"] * 1_000_000

        stats["sequenced_vs_planned"] = None
        idx = (stats["num_reads"].notna()) & (stats["num_planned_reads"].notna()) & (stats["num_planned_reads"] > 0)
        stats.loc[idx, "sequenced_vs_planned"] = (
            stats.loc[idx, "num_reads"] / stats.loc[idx, "num_planned_reads"] * 100.0
        ).astype(pd.Float64Dtype()).round(1)
        
        return stats
    
    @DBBlueprint.transaction
    def match_barcodes_to_kit(self, sequences: list[str], barcode_type: C.BarcodeType, index_type: C.IndexType | None = None) -> pd.DataFrame:
        unique_sequences = list(set(sequences))
        num_sequences = len(unique_sequences)
        
        if num_sequences == 0:
            return pd.DataFrame()

        query = Q.pd.match_barcodes_to_kit(
            unique_sequences, num_sequences,
            barcode_type_id=barcode_type.id,
            index_type_id=index_type.id if index_type is not None else None,
        )

        df = pd.read_sql(query, self.db.session.connection())
        return df
    
    @DBBlueprint.transaction
    def get_library_properties(self, project_id: int | None = None, seq_request_id: int | None = None, expand_properties: bool = True) -> pd.DataFrame:
        if project_id is None and seq_request_id is None:
            raise ValueError("At least one of project_id or seq_request_id must be provided.")
        
        query = Q.pd.library_properties(project_id=project_id, seq_request_id=seq_request_id)
        df = pd.read_sql(query, self.db.session.connection())
        if expand_properties and not df.empty:
            expanded = df["properties"].apply(pd.Series)
            for col in expanded.columns:
                expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

            df = pd.concat([df.drop(columns=["properties"]), expanded], axis=1)
        return df
    

    @DBBlueprint.transaction
    def get_library_data_qc(self, library_id: int | None = None, expand: bool = True) -> pd.DataFrame:
        query = Q.pd.library_data_qc(library_id)
        df = pd.read_sql(query, self.db.session.connection())
        df["library_type"] = C.LibraryType.map_series(df["library_type_id"])
        df["pool_type"] = C.PoolType.map_series(df["pool_type_id"])
        if expand and not df.empty:
            expanded = df["qc"].apply(pd.Series)
            for col in expanded.columns:
                expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

            df = pd.concat([df.drop(columns=["qc"]), expanded], axis=1)

        return df

    @DBBlueprint.transaction
    def query(self, query: sa.Select | str) -> pd.DataFrame:
        df = pd.read_sql(query, self.db.session.connection())
        return df

