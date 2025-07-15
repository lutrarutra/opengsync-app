from typing import TYPE_CHECKING

import pandas as pd

import sqlalchemy as sa
from sqlalchemy.sql.operators import and_  # noqa: F401

if TYPE_CHECKING:
    from .DBHandler import DBHandler

from .. import models
from .. import categories


def get_experiment_libraries_df(
    self: "DBHandler", experiment_id: int,
    include_sample: bool = False, include_index_kit: bool = False,
    include_seq_request: bool = False, collapse_lanes: bool = False,
    include_indices: bool = False, drop_empty_columns: bool = True,
    collapse_indicies: bool = True
) -> pd.DataFrame:
        
    columns = [
        models.Experiment.id.label("experiment_id"), models.Experiment.name.label("experiment_name"),
        models.Lane.number.label("lane"), models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("reference_id"), models.Library.sample_name.label("sample_name"),
    ]

    if include_indices:
        columns.extend([
            models.LibraryIndex.sequence_i7.label("sequence_i7"), models.LibraryIndex.sequence_i5.label("sequence_i5"),
            models.LibraryIndex.name_i7.label("name_i7"), models.LibraryIndex.name_i5.label("name_i5"),
        ])

    if include_seq_request:
        columns.extend([
            models.SeqRequest.id.label("seq_request_id"), models.SeqRequest.name.label("request_name"),
            models.User.id.label("requestor_id"), models.User.email.label("requestor_email"),
        ])

    if include_index_kit:
        columns.extend([
            models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
        ])

    if include_sample:
        columns.extend([
            models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
            models.links.SampleLibraryLink.mux.label("mux"), models.links.SampleLibraryLink.mux_type_id.label("mux_type_id"),
        ])

    query = sa.select(*columns).where(
        models.Experiment.id == experiment_id
    ).join(
        models.Lane,
        models.Lane.experiment_id == models.Experiment.id
    ).join(
        models.links.LanePoolLink,
        models.links.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.links.LanePoolLink.pool_id
    ).join(
        models.Library,
        models.Library.pool_id == models.Pool.id
    )

    if include_indices:
        query = query.join(
            models.LibraryIndex,
            models.LibraryIndex.library_id == models.Library.id,
        )

    if include_sample:
        query = query.join(
            models.links.SampleLibraryLink,
            models.links.SampleLibraryLink.library_id == models.Library.id,
        ).join(
            models.Sample,
            models.Sample.id == models.links.SampleLibraryLink.sample_id,
        )

    if include_seq_request:
        query = query.join(
            models.SeqRequest,
            models.SeqRequest.id == models.Library.seq_request_id,
        ).join(
            models.User,
            models.User.id == models.SeqRequest.requestor_id,
        )
            
    query = query.order_by(models.Lane.number, models.Pool.id, models.Library.id)
    df = pd.read_sql(query, self._engine)

    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)  # type: ignore
    df["reference"] = df["reference_id"].map(categories.GenomeRef.get)  # type: ignore
    if "mux_type_id" in df.columns:
        df["mux_type"] = df["mux_type_id"].apply(lambda x: categories.MUXType.get(x) if pd.notna(x) else None)  # type: ignore

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


def get_flowcell_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    columns = [
        models.Experiment.id.label("experiment_id"), models.Experiment.name.label("experiment_name"),
        models.Lane.number.label("lane"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.Library.sample_name.label("sample_name"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("reference_id"),
        models.Library.seq_request_id.label("seq_request_id"),
        models.LibraryIndex.sequence_i7.label("sequence_i7"), models.LibraryIndex.sequence_i5.label("sequence_i5"),
        models.LibraryIndex.name_i7.label("name_i7"), models.LibraryIndex.name_i5.label("name_i5"),
    ]

    query = sa.select(*columns).where(
        models.Experiment.id == experiment_id
    ).join(
        models.Lane,
        models.Lane.experiment_id == models.Experiment.id,
    ).join(
        models.links.LanePoolLink,
        models.links.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.links.LanePoolLink.pool_id
    ).join(
        models.Library,
        models.Library.pool_id == models.Pool.id,
    ).join(
        models.LibraryIndex,
        models.LibraryIndex.library_id == models.Library.id,
    )

    query = query.order_by(models.Lane.number, models.Pool.id, models.Library.id)
    df = pd.read_sql(query, self._engine)
    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)  # type: ignore
    df["reference"] = df["reference_id"].map(categories.GenomeRef.get)  # type: ignore

    df = df[["lane", "sample_name", "library_name", "library_type", "reference", "seq_request_id", "sequence_i7", "sequence_i5"]]

    return df


def get_experiment_barcodes_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Lane.id.label("lane_id"), models.Lane.number.label("lane"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.sample_name.label("sample_name"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.LibraryIndex.sequence_i7.label("sequence_i7"), models.LibraryIndex.sequence_i5.label("sequence_i5"),
        models.LibraryIndex.name_i7.label("name_i7"), models.LibraryIndex.name_i5.label("name_i5"),
    ).where(
        models.Lane.experiment_id == experiment_id
    ).join(
        models.links.LanePoolLink,
        models.links.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.links.LanePoolLink.pool_id
    ).join(
        models.Library,
        models.Library.pool_id == models.Pool.id
    ).join(
        models.LibraryIndex,
        models.LibraryIndex.library_id == models.Library.id
    )

    df = pd.read_sql(query, self._engine)

    return df


def get_experiment_pools_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Pool.id, models.Pool.name,
        models.Pool.status_id, models.Pool.num_libraries,
        models.Pool.num_m_reads_requested, models.Pool.qubit_concentration,
        models.Pool.avg_fragment_size,
    ).where(
        models.Pool.experiment_id == experiment_id
    )

    df = pd.read_sql(query, self._engine)
    df["status"] = df["status_id"].map(categories.PoolStatus.get)  # type: ignore

    return df


def get_plate_df(self: "DBHandler", plate_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Plate.id, models.Plate.name, models.links.SamplePlateLink.well_idx,
        models.links.SamplePlateLink.sample_id, models.links.SamplePlateLink.library_id,
        models.Sample.name.label("sample_name"), models.Library.name.label("library_name"),
    ).where(
        models.Plate.id == plate_id
    ).join(
        models.links.SamplePlateLink,
        models.links.SamplePlateLink.plate_id == models.Plate.id
    ).join(
        models.Sample,
        models.Sample.id == models.links.SamplePlateLink.sample_id,
        isouter=True
    ).join(
        models.Library,
        models.Library.id == models.links.SamplePlateLink.library_id,
        isouter=True
    )

    df = pd.read_sql(query, self._engine)
    return df


def get_experiment_lanes_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Lane.id, models.Lane.number.label("lane"),
        models.Lane.phi_x, models.Lane.original_qubit_concentration, models.Lane.total_volume_ul,
        models.Lane.library_volume_ul, models.Lane.avg_fragment_size, models.Lane.sequencing_qubit_concentration,
        models.Lane.target_molarity
    ).where(
        models.Lane.experiment_id == experiment_id
    ).order_by(models.Lane.number)

    df = pd.read_sql(query, self._engine)

    return df


def get_experiment_laned_pools_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Lane.id.label("lane_id"), models.Lane.number.label("lane"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.Pool.num_m_reads_requested, models.Pool.qubit_concentration,
        models.Pool.avg_fragment_size, models.links.LanePoolLink.num_m_reads,
        models.PoolDilution.id.label("dilution_id"), models.PoolDilution.identifier.label("dilution"),
    ).where(
        models.Lane.experiment_id == experiment_id
    ).join(
        models.links.LanePoolLink,
        models.links.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.links.LanePoolLink.pool_id
    ).join(
        models.dilutions.PoolDilution,
        models.dilutions.PoolDilution.id == models.links.LanePoolLink.dilution_id,
        isouter=True
    )

    df = pd.read_sql(query, self._engine)

    return df


def get_pool_libraries_df(self: "DBHandler", pool_id: int) -> pd.DataFrame:
    columns = [
        models.Pool.id.label("pool_id"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.LibraryIndex.name_i7.label("name_i7"), models.LibraryIndex.name_i5.label("name_i5"),
        models.LibraryIndex.sequence_i7.label("sequence_i7"), models.LibraryIndex.sequence_i5.label("sequence_i5"),
    ]
    query = sa.select(*columns).where(
        models.Pool.id == pool_id
    ).join(
        models.Library,
        models.Library.pool_id == models.Pool.id
    ).join(
        models.LibraryIndex,
        models.LibraryIndex.library_id == models.Library.id,
        isouter=True
    )

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query, self._engine).drop(columns=["pool_id"])

    df = df.groupby(df.columns.difference(["name_i7", "sequence_i7", "name_i5", "sequence_i5"]).tolist(), as_index=False, dropna=False).agg({"name_i7": list, "sequence_i7": list, "name_i5": list, "sequence_i5": list}).rename(columns={"name_i7": "names_i7", "sequence_i7": "sequences_i7", "name_i5": "names_i5", "sequence_i5": "sequences_i5"})

    return df


def get_seq_requestor_df(self: "DBHandler", seq_request: int) -> pd.DataFrame:
    query = sa.select(
        models.SeqRequest.name.label("seq_request_name"),
        models.User.id.label("user_id"), models.User.email.label("email"),
        models.User.first_name.label("first_name"), models.User.last_name.label("last_name"),
        models.User.role_id.label("role_id")
    ).join(
        models.User,
        models.User.id == models.SeqRequest.requestor_id,
    ).where(
        models.SeqRequest.id == seq_request
    )

    df = pd.read_sql(query, self._engine)
    df["role"] = df["role_id"].map(categories.UserRole.get)  # type: ignore

    return df


def get_seq_request_share_emails_df(self: "DBHandler", seq_request: int) -> pd.DataFrame:
    query = sa.select(
        models.links.SeqRequestDeliveryEmailLink.email.label("email"),
        models.links.SeqRequestDeliveryEmailLink.status_id.label("status_id"),
    ).where(
        models.links.SeqRequestDeliveryEmailLink.seq_request_id == seq_request
    )

    df = pd.read_sql(query, self._engine)
    df["status"] = df["status_id"].map(categories.DeliveryStatus.get)  # type: ignore

    return df


def get_library_features_df(self: "DBHandler", library_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Feature.id.label("feature_id"), models.Feature.name.label("feature_name"), models.Feature.type_id.label("feature_type_id"),
        models.Feature.target_id.label("target_id"), models.Feature.target_name.label("target_name"),
        models.Feature.sequence.label("sequence"), models.Feature.pattern.label("pattern"), models.Feature.read.label("read"),
        models.FeatureKit.id.label("feature_kit_id"), models.FeatureKit.name.label("feature_kit_name"),
    ).join(
        models.FeatureKit,
        models.FeatureKit.id == models.Feature.feature_kit_id,
        isouter=True
    ).join(
        models.links.LibraryFeatureLink,
        models.links.LibraryFeatureLink.feature_id == models.Feature.id
    ).where(
        models.links.LibraryFeatureLink.library_id == library_id
    ).distinct()

    df = pd.read_sql(query, self._engine)
    df["feature_type"] = df["feature_type_id"].map(categories.FeatureType.get)  # type: ignore

    return df


def get_library_samples_df(self: "DBHandler", library_id: int, expand_attributes: bool = True) -> pd.DataFrame:
    query = sa.select(
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"), models.Sample._attributes.label("attributes"),
    ).join(
        models.links.SampleLibraryLink,
        models.links.SampleLibraryLink.sample_id == models.Sample.id
    ).where(
        models.links.SampleLibraryLink.library_id == library_id
    )

    df = pd.read_sql(query, self._engine)
    if expand_attributes:
        expanded = df["attributes"].apply(pd.Series)
        for col in expanded.columns:
            expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

        df = pd.concat([df.drop(columns=["attributes"]), expanded], axis=1)

    return df


def get_library_mux_table_df(self: "DBHandler", library_id: int) -> pd.DataFrame:
    query = sa.select(
        models.links.SampleLibraryLink.sample_id.label("sample_id"), models.Sample.name.label("sample_name"),
        models.links.SampleLibraryLink.mux.label("mux"), models.links.SampleLibraryLink.mux_type_id.label("mux_type_id"),
    ).join(
        models.Sample,
        models.Sample.id == models.links.SampleLibraryLink.sample_id
    ).where(
        models.links.SampleLibraryLink.library_id == library_id
    )

    df = pd.read_sql(query, self._engine)
    df["mux_type"] = df["mux_type_id"].apply(lambda x: categories.MUXType.get(x) if pd.notna(x) else None)  # type: ignore

    expanded = df["mux"].apply(pd.Series)
    for col in expanded.columns:
        expanded[col] = expanded[col].apply(lambda x: x if isinstance(x, dict) else x)

    return df


def get_seq_request_libraries_df(
    self: "DBHandler", seq_request_id: int, include_indices: bool = False,
    collapse_indicies: bool = False
) -> pd.DataFrame:
    
    columns = [
        models.SeqRequest.id.label("seq_request_id"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("genome_ref_id"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
    ]

    if include_indices:
        columns.extend([
            models.LibraryIndex.sequence_i7.label("sequence_i7"), models.LibraryIndex.sequence_i5.label("sequence_i5"),
            models.LibraryIndex.name_i7.label("name_i7"), models.LibraryIndex.name_i5.label("name_i5"),
        ])
    
    query = sa.select(*columns).where(
        models.SeqRequest.id == seq_request_id
    ).join(
        models.Library,
        models.Library.seq_request_id == models.SeqRequest.id
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id
    )

    if include_indices:
        query = query.join(
            models.LibraryIndex,
            models.LibraryIndex.library_id == models.Library.id,
        )

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query, self._engine)

    if include_indices and collapse_indicies:
        df = df.groupby(df.columns.difference(["sequence_i7", "sequence_i5", "name_i7", "name_i5"]).tolist(), as_index=False).agg({"sequence_i7": list, "sequence_i5": list, "name_i7": list, "name_i5": list}).copy().rename(
            columns={
                "sequence_i7": "sequences_i7", "sequence_i5": "sequences_i5",
                "name_i7": "names_i7", "name_i5": "names_i5"
            }
        )

    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)  # type: ignore
    df["genome_ref"] = df["genome_ref_id"].apply(lambda x: categories.LibraryType.get(x) if pd.notna(x) else None)  # type: ignore

    return df


def get_seq_request_samples_df(
    self: "DBHandler", seq_request_id: int
) -> pd.DataFrame:
    query = sa.select(
        models.SeqRequest.id.label("seq_request_id"),
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
        models.links.SampleLibraryLink.mux.label("mux"), models.links.SampleLibraryLink.mux_type_id.label("mux_type_id"),
        models.Library.id.label("library_id"), models.Library.name.label("library_name"), models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("genome_ref_id"),
        models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
    ).where(
        models.SeqRequest.id == seq_request_id
    ).join(
        models.Library,
        models.Library.seq_request_id == models.SeqRequest.id
    ).join(
        models.Pool,
        models.Pool.id == models.Library.pool_id,
        isouter=True
    ).join(
        models.links.SampleLibraryLink,
        models.links.SampleLibraryLink.library_id == models.Library.id,
    ).join(
        models.Sample,
        models.Sample.id == models.links.SampleLibraryLink.sample_id,
    )

    query = query.order_by(models.Library.id)

    df = pd.read_sql(query, self._engine)

    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)  # type: ignore
    df["genome_ref"] = df["genome_ref_id"].apply(lambda x: categories.LibraryType.get(x) if pd.notna(x) else None)  # type: ignore
    df["mux_type"] = df["mux_type_id"].apply(lambda x: categories.MUXType.get(x) if pd.notna(x) else None)  # type: ignore

    return df


def get_experiment_seq_qualities_df(self: "DBHandler", experiment_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.SeqQuality.lane, models.SeqQuality.num_lane_reads, models.SeqQuality.num_library_reads,
        models.SeqQuality.mean_quality_pf_r1, models.SeqQuality.q30_perc_r1,
        models.SeqQuality.mean_quality_pf_r2, models.SeqQuality.q30_perc_r2,
        models.SeqQuality.mean_quality_pf_i1, models.SeqQuality.q30_perc_i1,
        models.SeqQuality.mean_quality_pf_i2, models.SeqQuality.q30_perc_i2,
    ).join(
        models.Library,
        models.Library.id == models.SeqQuality.library_id,
        isouter=True
    ).where(
        models.SeqQuality.experiment_id == experiment_id
    )

    query = query.order_by(models.SeqQuality.lane, models.Library.id)
    df = pd.read_sql(query, self._engine)

    df.loc[df["library_name"].isna(), "library_id"] = -1
    df.loc[df["library_name"].isna(), "library_name"] = "Undetermined"
    df["library_id"] = df["library_id"].astype(int)

    return df


def get_index_kit_barcodes_df(self: "DBHandler", index_kit_id: int, per_adapter: bool = False, per_index: bool = False) -> pd.DataFrame:
    if per_index and per_adapter:
        raise ValueError("Cannot set both per_adapter and per_index to True.")
    
    query = sa.select(
        models.Barcode.id, models.Barcode.sequence.label("sequence"), models.Barcode.well.label("well"),
        models.Barcode.name.label("name"), models.Barcode.adapter_id.label("adapter_id"),
        models.Barcode.type_id.label("type_id"),
    ).where(
        models.Barcode.index_kit_id == index_kit_id
    )

    df = pd.read_sql(query, self._engine)
    df["name"] = df["name"].astype(str)
    df["type"] = df["type_id"].map(categories.BarcodeType.get)  # type: ignore

    if per_adapter or per_index:
        df = df.groupby(
            df.columns.difference(["id", "sequence", "name", "type_id", "type"]).tolist(), as_index=False, dropna=False
        ).agg(
            {"id": list, "sequence": list, "name": list, "type_id": list, "type": list}
        ).rename(
            columns={"id": "ids", "sequence": "sequences", "name": "names", "type_id": "type_ids", "type": "types"}
        )

    if per_index:
        if (index_kit := self.get_index_kit(index_kit_id)) is None:
            raise ValueError(f"Index kit with ID {index_kit_id} not found.")
        
        if index_kit.type == categories.IndexType.TENX_ATAC_INDEX:
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
        elif index_kit.type == categories.IndexType.DUAL_INDEX:
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
                    if row["types"][i] == categories.BarcodeType.INDEX_I7:
                        barcode_data["name_i7"].append(row["names"][i])
                        barcode_data["sequence_i7"].append(row["sequences"][i])
                    else:
                        barcode_data["name_i5"].append(row["names"][i])
                        barcode_data["sequence_i5"].append(row["sequences"][i])
        elif index_kit.type == categories.IndexType.SINGLE_INDEX:
            barcode_data = {
                "well": [],
                "adapter_id": [],
                "name": [],
                "sequence_i7": [],
            }
            for _, row in df.iterrows():
                barcode_data["adapter_id"].append(row["adapter_id"])
                barcode_data["well"].append(row["well"])
                barcode_data["name"].append(row["names"][0])
                barcode_data["sequence_i7"].append(row["sequences"][0])

        df = pd.DataFrame(barcode_data)

    return df


def get_feature_kit_features_df(self: "DBHandler", feature_kit_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Feature.id.label("feature_id"), models.Feature.name.label("name"),
        models.Feature.sequence.label("sequence"), models.Feature.pattern.label("pattern"), models.Feature.read.label("read"),
        models.Feature.type_id.label("type_id"),
        models.Feature.target_name.label("target_name"), models.Feature.target_id.label("target_id"),
    ).where(
        models.Feature.feature_kit_id == feature_kit_id
    )

    df = pd.read_sql(query, self._engine)
    df["type"] = df["type_id"].map(categories.FeatureType.get)  # type: ignore

    return df


def get_seq_request_features_df(self: "DBHandler", seq_request_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.Library.sample_name.label("sample_name"),
        models.Feature.id.label("feature_id"), models.Feature.name.label("feature_name"),
        models.Feature.sequence.label("sequence"), models.Feature.pattern.label("pattern"), models.Feature.read.label("read"),
        models.Feature.type_id.label("type_id"), models.Feature.target_name.label("target_name"), models.Feature.target_id.label("target_id"),
    )

    query = query.where(
        models.Library.seq_request_id == seq_request_id
    ).join(
        models.links.LibraryFeatureLink,
        models.links.LibraryFeatureLink.library_id == models.Library.id
    ).join(
        models.Feature,
        models.Feature.id == models.links.LibraryFeatureLink.feature_id
    )

    df = pd.read_sql(query, self._engine)
    df["type"] = df["type_id"].map(categories.FeatureType.get)  # type: ignore

    return df


def get_project_samples_df(self: "DBHandler", project_id: int, pivot: bool = True) -> pd.DataFrame:
    query = sa.select(
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
        models.Sample._attributes.label("attributes"),
    ).where(models.Sample.project_id == project_id)
    
    df = pd.read_sql(query, self._engine)
    if pivot:
        expanded = df["attributes"].apply(pd.Series)
        for col in expanded.columns:
            expanded[col] = expanded[col].apply(lambda x: x.get("value") if isinstance(x, dict) else x)

        df = pd.concat([df.drop(columns=["attributes"]), expanded], axis=1)
    return df


def get_project_libraries_df(self: "DBHandler", project_id: int, collapse_lanes: bool = True) -> pd.DataFrame:
    query = sa.select(
        models.Library.experiment_id.label("experiment_id"),
        models.Library.id.label("library_id"),
        models.Library.name.label("library_name"),
        models.Library.sample_name.label("sample_pool"),
        models.Library.type_id.label("library_type_id"),
        models.Library.genome_ref_id.label("genome_ref_id"),
        models.Library.seq_request_id.label("seq_request_id"),

        models.Sample.id.label("sample_id"),
        models.Sample.name.label("sample_name"),

        models.links.SampleLibraryLink.mux.label("mux"),
        models.links.SampleLibraryLink.mux_type_id.label("mux_type_id"),
    ).where(
        models.Sample.project_id == project_id
    ).join(
        models.links.SampleLibraryLink,
        models.links.SampleLibraryLink.sample_id == models.Sample.id
    ).join(
        models.Library,
        models.Library.id == models.links.SampleLibraryLink.library_id
    )

    libraries = pd.read_sql(query, self._engine)
    experiment_ids = libraries["experiment_id"].unique().tolist()
    libraries_ids = libraries["library_id"].unique().tolist()

    libraries["mux_type"] = libraries["mux_type_id"].apply(lambda x: categories.MUXType.get(x) if pd.notna(x) else None)  # type: ignore
    libraries["genome_ref"] = libraries["genome_ref_id"].map(categories.GenomeRef.get)  # type: ignore
    libraries["library_type"] = libraries["library_type_id"].map(categories.LibraryType.get)  # type: ignore

    query = sa.select(
        models.Experiment.id.label("experiment_id"), models.Experiment.name.label("experiment_name"),
        models.Lane.number.label("lane"), models.Pool.id.label("pool_id"), models.Pool.name.label("pool_name"),
        models.Library.id.label("library_id")
    ).where(
        and_(models.Experiment.id.in_(experiment_ids), models.Library.id.in_(libraries_ids))
    ).join(
        models.Lane,
        models.Lane.experiment_id == models.Experiment.id
    ).join(
        models.links.LanePoolLink,
        models.links.LanePoolLink.lane_id == models.Lane.id
    ).join(
        models.Pool,
        models.Pool.id == models.links.LanePoolLink.pool_id
    ).join(
        models.Library,
        models.Library.pool_id == models.Pool.id
    )
    
    lanes = pd.read_sql(query, self._engine)
    if collapse_lanes:
        order = [
            "sample_name", "library_name", "sample_pool",
            "library_type", "genome_ref", "experiment_name", "lanes",
            "mux", "mux_type", "library_id", "sample_id", "seq_request_id"
        ]
        lanes = lanes.groupby(
            lanes.columns.difference(["lane"]).tolist(), as_index=False, dropna=False
        ).agg({"lane": list}).rename(columns={"lane": "lanes"})
    else:
        order = [
            "sample_name", "library_name", "sample_pool",
            "library_type", "genome_ref", "experiment_name", "lane",
            "mux", "mux_type", "library_id", "sample_id", "seq_request_id"
        ]

    merged = pd.merge(lanes, libraries, on=["library_id", "experiment_id"], how="left")
    return merged[order]


def get_lab_prep_libraries_df(self: "DBHandler", lab_prep_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("id"),
        models.Library.name.label("name"),
        models.Library.status_id.label("status_id"),
        models.Library.type_id.label("type_id"),
        models.Library.genome_ref_id.label("genome_ref_id"),
        models.Library.sample_name.label("sample_name"),
    ).where(
        models.Library.lab_prep_id == lab_prep_id
    )

    df = pd.read_sql(query, self._engine)
    df["status"] = df["status_id"].map(categories.LibraryStatus.get)  # type: ignore
    df["type"] = df["type_id"].map(categories.LibraryType.get)  # type: ignore
    df["genome_ref"] = df["genome_ref_id"].map(categories.GenomeRef.get)  # type: ignore
    return df


def get_lab_prep_samples_df(self: "DBHandler", lab_prep_id: int) -> pd.DataFrame:
    query = sa.select(
        models.Library.id.label("library_id"), models.Library.name.label("library_name"),
        models.Library.type_id.label("library_type_id"), models.Library.sample_name.label("sample_pool"),
        models.Library.mux_type_id.label("mux_type_id"),
        models.Sample.id.label("sample_id"), models.Sample.name.label("sample_name"),
        models.links.SampleLibraryLink.mux.label("mux"),
    ).where(
        models.Library.lab_prep_id == lab_prep_id
    ).join(
        models.links.SampleLibraryLink,
        models.links.SampleLibraryLink.library_id == models.Library.id
    ).join(
        models.Sample,
        models.Sample.id == models.links.SampleLibraryLink.sample_id,
    )

    df = pd.read_sql(query, self._engine).sort_values(["library_id", "sample_id"])
    df["library_type"] = df["library_type_id"].map(categories.LibraryType.get)  # type: ignore
    df["mux_type"] = df["mux_type_id"].apply(lambda x: categories.MUXType.get(x) if pd.notna(x) else None)  # type: ignore
    return df


def query_barcode_sequences_df(self: "DBHandler", sequence: str, limit: int = 10) -> pd.DataFrame:
    query = sa.select(
        models.Barcode.id.label("id"), models.Barcode.sequence.label("sequence"),
        models.Barcode.well.label("well"), models.Barcode.name.label("name"),
        models.Barcode.type_id.label("type_id"),
        models.IndexKit.id.label("index_kit_id"), models.IndexKit.name.label("index_kit_name"),
    ).join(
        models.IndexKit,
        models.IndexKit.id == models.Barcode.index_kit_id
    )

    query = query.order_by(
        sa.func.similarity(models.Barcode.sequence, sequence).desc()
    ).limit(limit)

    df = pd.read_sql(query, self._engine)
    
    def hamming_distance(str1: str, str2: str) -> int:
        min_length = min(len(str1), len(str2))
        distance = sum(c1 != c2 for c1, c2 in zip(str1[:min_length], str2[:min_length]))
        distance += abs(len(str1) - len(str2))
        return distance

    df["hamming"] = df["sequence"].apply(lambda x: hamming_distance(x, sequence))
    df["type"] = df["type_id"].map(categories.BarcodeType.get)  # type: ignore

    return df