import pandas as pd
from limbless import models

def add_index_kits(db_handler):
    db_handler.open_session()
    db_handler._session.query(models.SeqKit).delete()
    db_handler._session.query(models.SeqIndex).delete()
    db_handler._session.commit()
    db_handler.close_session()

    df = pd.read_csv("data/10x_kits/Dual_Index_Kit_NN_Set_A.csv", comment="#", index_col=0)

    seq_kit = db_handler.create_seqkit(
        name="10x Dual Index Kit NN Set A",
    )

    for adapter, row in df.iterrows():
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=df.columns[i],
            ) 

    df = pd.read_csv("data/10x_kits/Dual_Index_Kit_NT_Set_A.csv", comment="#", index_col=0)

    seq_kit = db_handler.create_seqkit(
        name="10x Dual Index Kit NT Set A",
    )

    for adapter, row in df.iterrows():
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=df.columns[i],
            )


    df = pd.read_csv("data/10x_kits/Dual_Index_Kit_TN_Set_A.csv", comment="#", index_col=0)

    seq_kit = db_handler.create_seqkit(
        name = "10x Dual Index Kit TN Seq A"
    )

    for adapter, row in df.iterrows():
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=df.columns[i],
            )

    df = pd.read_csv("data/10x_kits/Dual_Index_Kit_TT_Set_A.csv", comment="#", index_col=0)

    seq_kit = db_handler.create_seqkit(
        name = "10x Dual Index Kit TT Seq A"
    )

    for adapter, row in df.iterrows():
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=df.columns[i],
            )

    df = pd.read_csv("data/10x_kits/Single_Index_Kit_N_Set_A.csv", index_col=0, header=None)

    seq_kit = db_handler.create_seqkit(
        name = "10x Single Index Kit N Seq A"
    )

    for adapter, row in df.iterrows():
        cols = [f"single_index_{i+1}" for i in range(1, 5)]
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=cols[i],
            )

    df = pd.read_csv("data/10x_kits/Single_Index_Kit_T_Set_A.csv", index_col=0, header=None)

    seq_kit = db_handler.create_seqkit(
        name = "10x Single Index Kit T Seq A"
    )

    for adapter, row in df.iterrows():
        cols = [f"single_index_{i+1}" for i in range(1, 5)]
        for i, seq in enumerate(row.values):
            db_handler.create_seqindex(
                    sequence=seq,
                    adapter=adapter,
                    seq_kit_id=seq_kit.id,
                    type=cols[i],
            )