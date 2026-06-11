"""Shared post-processing transforms for pandas DataFrame queries.

Each function takes a raw DataFrame (from pd.read_sql) and returns a
processed DataFrame.  These are pure functions with no session awareness —
they are consumed by both SyncPandas and AsyncPandas.
"""

from __future__ import annotations

import pandas as pd

from ... import categories as C


# ======================================================================
# Low-level helpers
# ======================================================================

def expand_json_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Expand a JSON column into separate columns, extracting 'value' keys."""
    if column not in df.columns or df.empty:
        return df
    expanded = df[column].apply(pd.Series)
    for col in expanded.columns:
        expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)
    return pd.concat([df.drop(columns=[column]), expanded], axis=1)


def expand_json_column_raw(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Expand a JSON column into separate columns, keeping dicts as-is."""
    if column not in df.columns or df.empty:
        return df
    expanded = df[column].apply(pd.Series)
    for col in expanded.columns:
        expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)
    return pd.concat([df, expanded], axis=1)


def expand_mux(df: pd.DataFrame, column: str = "mux") -> pd.DataFrame:
    """Expand a mux JSON column, preserving dict structure."""
    return expand_json_column_raw(df, column)


def collapse_indices(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse per-barcode index rows into lists per library."""
    idx_cols = ["sequence_i7", "sequence_i5", "name_i7", "name_i5"]
    return df.groupby(
        df.columns.difference(idx_cols).tolist(), as_index=False
    ).agg({c: list for c in idx_cols}).copy().rename(
        columns={
            "sequence_i7": "sequences_i7", "sequence_i5": "sequences_i5",
            "name_i7": "names_i7", "name_i5": "names_i5",
        }
    )


def collapse_lanes(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse lane numbers into a list column."""
    return df.groupby(
        df.columns.difference(["lane"]).tolist(), as_index=False
    ).agg({"lane": list}).rename(columns={"lane": "lanes"})


def hamming_distance(str1: str, str2: str) -> int:
    min_length = min(len(str1), len(str2))
    distance = sum(c1 != c2 for c1, c2 in zip(str1[:min_length], str2[:min_length]))
    distance += abs(len(str1) - len(str2))
    return distance


def expand_qc(df: pd.DataFrame) -> pd.DataFrame:
    """Expand a 'qc' JSON column and drop the original."""
    if "qc" not in df.columns or df.empty:
        return df
    expanded = df["qc"].apply(pd.Series)
    for col in expanded.columns:
        expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)
    df = pd.concat([df.drop(columns=["qc"]), expanded], axis=1)
    return df


def weighted_groupby(
    df: pd.DataFrame,
    group_cols: list[str],
    exclude_cols: list[str],
    weight_col: str = "num_reads",
) -> pd.DataFrame:
    """Collapse rows with a weighted average for numeric cols, 'first' for others."""
    df["weight"] = df[weight_col] / df.groupby(group_cols, dropna=False)[weight_col].transform("sum")
    agg_dict: dict = {weight_col: "sum"}
    agg_dict |= {
        col: (lambda x: (x * df.loc[x.index, "weight"]).sum() if pd.api.types.is_numeric_dtype(x) else x.iloc[0])
        for col in df.columns
        if col not in exclude_cols + ["weight", weight_col]
    }
    df = df.groupby(group_cols, as_index=False, dropna=False).agg(agg_dict)
    return df


# ======================================================================
# Per-method transforms
# ======================================================================

def experiment_libraries(
    df: pd.DataFrame,
    include_indices: bool,
    collapse_indicies: bool,
    drop_empty_columns: bool,
    collapse_lanes_: bool,
) -> pd.DataFrame:
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
        df = collapse_indices(df)

    if drop_empty_columns:
        df = df.dropna(axis="columns", how="all")

    if collapse_lanes_:
        df = collapse_lanes(df)
        order[0] = "lanes"
        df = df[[c for c in order if c in df.columns]]

    return df


def flowcell(df: pd.DataFrame) -> pd.DataFrame:
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["reference"] = C.GenomeRef.map_series(df["reference_id"], na_action="ignore")
    df["orientation"] = C.BarcodeOrientation.map_series(df["orientation_id"], na_action="ignore")
    df = df[["lane", "sample_name", "library_name", "library_type", "reference", "seq_request_id", "sequence_i7", "sequence_i5", "orientation", "read_structure", "protocol_name", "pool_name", "library_id"]]
    return df


def experiment_barcodes(df: pd.DataFrame) -> pd.DataFrame:
    df["orientation"] = C.BarcodeOrientation.map_series(df["orientation_id"], na_action="ignore")
    return df


def experiment_pools(df: pd.DataFrame) -> pd.DataFrame:
    df["status"] = C.PoolStatus.map_series(df["status_id"], na_action="ignore")
    return df


def experiment_seq_qualities(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[df["library_id"].isna(), "library_name"] = "Undetermined"
    df["library_id"] = df["library_id"].astype(pd.Int64Dtype())
    return df


def experiment_stats(
    df: pd.DataFrame, per_lane: bool, expand_qc_: bool, weighted_average: bool,
) -> pd.DataFrame:
    df["library_id"] = df["library_id"].astype(pd.Int64Dtype())

    if expand_qc_:
        df = expand_qc(df)

    if not per_lane:
        df = df.drop(columns=["lane"])
        group_cols = ["library_id", "library_name"]
        exclude = group_cols + ["num_reads", "weight"]
        df = weighted_groupby(df, group_cols, exclude)

    return df


def project_samples(df: pd.DataFrame, pivot: bool) -> pd.DataFrame:
    if pivot:
        df = expand_json_column(df, "attributes")
    return df


def project_seq_requests(df: pd.DataFrame) -> pd.DataFrame:
    df["status"] = C.SeqRequestStatus.map_series(df["status_id"], na_action="ignore")
    return df


def project_features(df: pd.DataFrame) -> pd.DataFrame:
    df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")
    return df


def project_latest_request_share_emails(df: pd.DataFrame) -> pd.DataFrame:
    df["status"] = C.DeliveryStatus.map_series(df["status_id"], na_action="ignore")
    return df


def project_libraries(libraries: pd.DataFrame, lanes: pd.DataFrame, collapse_lanes_: bool) -> pd.DataFrame:
    libraries["mux_type"] = C.MUXType.map_series(libraries["mux_type_id"], na_action="ignore")
    libraries["genome_ref"] = C.GenomeRef.map_series(libraries["genome_ref_id"], na_action="ignore")
    libraries["library_type"] = C.LibraryType.map_series(libraries["library_type_id"], na_action="ignore")

    if collapse_lanes_:
        order = [
            "sample_name", "library_name", "sample_pool",
            "library_type", "genome_ref", "experiment_name", "lanes",
            "mux", "mux_type", "properties", "library_id", "sample_id", "seq_request_id",
        ]
        lanes = lanes.sort_values("lane").groupby(
            lanes.columns.difference(["lane"]).tolist(), as_index=False, dropna=False,
        ).agg({"lane": list}).rename(columns={"lane": "lanes"})
    else:
        order = [
            "sample_name", "library_name", "sample_pool",
            "library_type", "genome_ref", "experiment_name", "lane",
            "mux", "mux_type", "properties", "library_id", "sample_id", "seq_request_id",
        ]

    merged = pd.merge(libraries, lanes, on=["library_id", "experiment_id"], how="left")
    return merged[order].copy()


def seq_requestor(df: pd.DataFrame) -> pd.DataFrame:
    df["role"] = C.UserRole.map_series(df["role_id"], na_action="ignore")
    return df


def seq_request_libraries(
    df: pd.DataFrame, include_indices: bool, collapse_indicies: bool,
) -> pd.DataFrame:
    if include_indices and collapse_indicies:
        df = collapse_indices(df)
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")
    return df


def seq_request_samples(df: pd.DataFrame) -> pd.DataFrame:
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")
    df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")
    return df


def seq_request_sample_table(df: pd.DataFrame) -> pd.DataFrame:
    if not df.empty:
        df = expand_json_column(df, "attributes")
    return df


def seq_request_features(df: pd.DataFrame) -> pd.DataFrame:
    df["type"] = C.FeatureType.map_series(df["type_id"], na_action="ignore")
    return df


def seq_request_share_emails(df: pd.DataFrame) -> pd.DataFrame:
    df["status"] = C.DeliveryStatus.map_series(df["status_id"], na_action="ignore")
    return df


def pool_num_reads_stats(
    sequenced_df: pd.DataFrame, planned_df: pd.DataFrame,
) -> pd.DataFrame:
    sequenced_df["pool_id"] = sequenced_df["pool_id"].astype(pd.Int64Dtype())

    stats = sequenced_df.groupby(
        ["pool_id", "pool_name"], dropna=False
    ).agg(
        num_reads=pd.NamedAgg(column="num_reads", aggfunc="sum"),
        num_m_reads_requested=pd.NamedAgg(column="num_m_reads_requested", aggfunc="first"),
    ).reset_index()

    planned_df["pool_id"] = planned_df["pool_id"].astype(pd.Int64Dtype())
    planned_reads = planned_df.groupby(
        ["pool_id"], dropna=False
    ).agg(
        num_m_reads_planned=pd.NamedAgg(column="num_m_reads", aggfunc="sum"),
    ).reset_index()
    stats = pd.merge(stats, planned_reads, on="pool_id", how="left")

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


def library_features(df: pd.DataFrame) -> pd.DataFrame:
    df["feature_type"] = C.FeatureType.map_series(df["feature_type_id"], na_action="ignore")
    return df


def library_samples(df: pd.DataFrame, expand_attributes: bool) -> pd.DataFrame:
    if expand_attributes:
        df = expand_json_column(df, "attributes")
    return df


def library_sample_pool(df: pd.DataFrame, expand_mux_: bool) -> pd.DataFrame:
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

    if expand_mux_ and not df.empty:
        expanded = df["mux"].apply(pd.Series)
        for col in expanded.columns:
            expanded[f"mux_{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)
        df = pd.concat([df, expanded], axis=1)
    return df


def library_stats(
    df: pd.DataFrame, per_lane: bool, expand_qc_: bool, weighted_average: bool,
) -> pd.DataFrame:
    if expand_qc_:
        df = expand_qc(df)

    if not per_lane:
        df = df.drop(columns=["lane"])
        df["weight"] = df["num_reads"] / df["num_reads"].sum()
        agg_dict: dict = {"num_reads": "sum"}
        if weighted_average:
            agg_dict |= {
                col: (lambda x: (x * df.loc[x.index, "weight"]).sum() if pd.api.types.is_numeric_dtype(x) else x.iloc[0])
                for col in df.columns if col not in ["num_reads", "weight"]
            }
        else:
            agg_dict |= {
                col: ("mean" if pd.api.types.is_numeric_dtype(df[col]) else "first")
                for col in df.columns if col not in ["num_reads", "weight"]
            }
        df["dummy"] = 0
        df = df.groupby(["dummy"], as_index=False).agg(agg_dict)
        df = df.drop(columns=["dummy"])

    return df


def library_properties(df: pd.DataFrame, expand_properties: bool) -> pd.DataFrame:
    if expand_properties and not df.empty:
        df = expand_json_column(df, "properties")
    return df


def library_data_qc(df: pd.DataFrame, expand: bool) -> pd.DataFrame:
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"])
    df["pool_type"] = C.PoolType.map_series(df["pool_type_id"])
    if expand and not df.empty:
        expanded = df["qc"].apply(pd.Series)
        for col in expanded.columns:
            expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)
        df = pd.concat([df.drop(columns=["qc"]), expanded], axis=1)
    return df


def lab_prep_libraries(df: pd.DataFrame) -> pd.DataFrame:
    df["status"] = C.LibraryStatus.map_series(df["status_id"], na_action="ignore")
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["genome_ref"] = C.GenomeRef.map_series(df["genome_ref_id"], na_action="ignore")
    df["index_type"] = C.IndexType.map_series(df["index_type_id"], na_action="ignore")
    return df


def lab_prep_barcodes(df: pd.DataFrame) -> pd.DataFrame:
    df["index_type"] = C.IndexType.map_series(df["index_type_id"], na_action="ignore")
    return df


def lab_prep_pooling_table(df: pd.DataFrame, expand_mux_: bool) -> pd.DataFrame:
    df = df.sort_values(["library_id", "sample_id"])
    df["library_type"] = C.LibraryType.map_series(df["library_type_id"], na_action="ignore")
    df["mux_type"] = C.MUXType.map_series(df["mux_type_id"], na_action="ignore")

    if expand_mux_ and not df.empty:
        expanded = df["mux"].apply(pd.Series)
        for col in expanded.columns:
            expanded[f"mux_{col}"] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)
        df = pd.concat([df, expanded], axis=1)
    return df


def query_barcode_sequences(df: pd.DataFrame, sequence: str, limit: int) -> pd.DataFrame:
    df["hamming"] = df["sequence"].apply(lambda x: hamming_distance(x, sequence))
    df["type"] = C.BarcodeType.map_series(df["type_id"], na_action="ignore")
    return df


def index_kit_barcodes(df: pd.DataFrame, per_adapter: bool, per_index: bool) -> pd.DataFrame:
    """Base transform for index kit barcodes (before per_index ORM lookup)."""
    df["name"] = df["name"].astype(str)
    df["well"] = df["well"].astype(str)
    df["type"] = C.BarcodeType.map_series(df["type_id"], na_action="ignore")

    if per_adapter or per_index:
        df = df.groupby(
            df.columns.difference(["id", "sequence", "name", "type_id", "type"]).tolist(),
            as_index=False, dropna=False,
        ).agg(
            {"id": list, "sequence": list, "name": list, "type_id": list, "type": list}
        ).rename(
            columns={"id": "ids", "sequence": "sequences", "name": "names", "type_id": "type_ids", "type": "types"}
        )

    return df


def index_kit_barcodes_per_index(df: pd.DataFrame, index_kit_type) -> pd.DataFrame:
    """Pivots grouped barcodes into wide-form based on index kit type."""
    if index_kit_type == C.IndexType.TENX_ATAC_INDEX:
        barcode_data: dict = {
            "well": [], "adapter_id": [], "name": [],
            "sequence_1": [], "sequence_2": [], "sequence_3": [], "sequence_4": [],
        }
        for _, row in df.iterrows():
            barcode_data["well"].append(row["well"])
            barcode_data["name"].append(row["names"][0])
            barcode_data["adapter_id"].append(row["adapter_id"])
            for i in range(4):
                barcode_data[f"sequence_{i + 1}"].append(row["sequences"][i])
    elif index_kit_type == C.IndexType.DUAL_INDEX:
        barcode_data = {
            "well": [], "adapter_id": [],
            "name_i7": [], "sequence_i7": [], "name_i5": [], "sequence_i5": [],
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
    elif index_kit_type == C.IndexType.COMBINATORIAL_DUAL_INDEX:
        barcode_data = {
            "adapter_id": [],
            "name_i7": [], "sequence_i7": [], "name_i5": [], "sequence_i5": [],
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
    elif index_kit_type == C.IndexType.SINGLE_INDEX_I7:
        barcode_data = {"well": [], "adapter_id": [], "name_i7": [], "sequence_i7": []}
        for _, row in df.iterrows():
            barcode_data["adapter_id"].append(row["adapter_id"])
            barcode_data["well"].append(row["well"])
            barcode_data["name_i7"].append(row["names"][0])
            barcode_data["sequence_i7"].append(row["sequences"][0])
    else:
        raise ValueError(f"Unsupported index kit type: {index_kit_type}")

    return pd.DataFrame(barcode_data)
