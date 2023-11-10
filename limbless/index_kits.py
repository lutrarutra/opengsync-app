import os

import pandas as pd

from limbless.core import DBHandler
from limbless.categories import LibraryType


def add_dual_indexes(db_handler: DBHandler, df, index_kit):
    for adapter_name, row in df.iterrows():
        for i, seq in enumerate(row.values):
            if "i7" in df.columns[i]:
                workflow = None
                _type = "i7"
            else:
                _type = "i5"
                workflow = " ".join(df.columns[i].split("_")[1:])
                workflow = workflow.removesuffix("(i5)").strip()

            db_handler.create_barcode(
                sequence=seq,
                adapter=adapter_name,
                index_kit_id=index_kit.id,
                type=_type,
                workflow=workflow
            )


def add_single_indexes(db_handler: DBHandler, df, index_kit):
    for adapter_name, row in df.iterrows():
        cols = [f"Index {i}" for i in range(1, 5)]
        for i, seq in enumerate(row.values):
            db_handler.create_barcode(
                sequence=seq,
                adapter=adapter_name,
                index_kit_id=index_kit.id,
                type=cols[i],
                workflow=None
            )


def add_index_kits(db_handler: DBHandler, datadir: str = ""):
    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Dual_Index_Kit_NN_Set_A.csv"), comment="#", index_col=0)
    if (index_kit := db_handler.get_index_kit_by_name("10x Dual Index Kit NN Set A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Dual Index Kit NN Set A",
            allowed_library_types=[LibraryType.DUAL_INDEX]
        )
    add_dual_indexes(db_handler, df, index_kit)

    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Dual_Index_Kit_NT_Set_A.csv"), comment="#", index_col=0)
    if (index_kit := db_handler.get_index_kit_by_name("10x Dual Index Kit NT Set A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Dual Index Kit NT Set A",
            allowed_library_types=[LibraryType.DUAL_INDEX]
        )
    add_dual_indexes(db_handler, df, index_kit)

    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Dual_Index_Kit_TN_Set_A.csv"), comment="#", index_col=0)
    if (index_kit := db_handler.get_index_kit_by_name("10x Dual Index Kit TN Seq A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Dual Index Kit TN Seq A",
            allowed_library_types=[LibraryType.DUAL_INDEX]
        )
    add_dual_indexes(db_handler, df, index_kit)

    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Dual_Index_Kit_TT_Set_A.csv"), comment="#", index_col=0)
    if (index_kit := db_handler.get_index_kit_by_name("10x Dual Index Kit TT Seq A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Dual Index Kit TT Seq A",
            allowed_library_types=[LibraryType.DUAL_INDEX]
        )
    add_dual_indexes(db_handler, df, index_kit)

    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Single_Index_Kit_N_Set_A.csv"), index_col=0, header=None)
    if (index_kit := db_handler.get_index_kit_by_name("10x Single Index Kit N Seq A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Single Index Kit N Seq A",
            allowed_library_types=[LibraryType.SINGLE_INDEX]
        )
    add_single_indexes(db_handler, df, index_kit)

    df = pd.read_csv(os.path.join(datadir, "10x_kits", "Single_Index_Kit_T_Set_A.csv"), index_col=0, header=None)
    if (index_kit := db_handler.get_index_kit_by_name("10x Single Index Kit T Seq A")) is None:
        index_kit = db_handler.create_index_kit(
            name="10x Single Index Kit T Seq A",
            allowed_library_types=[LibraryType.SINGLE_INDEX]
        )
    add_single_indexes(db_handler, df, index_kit)
