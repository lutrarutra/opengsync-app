import os
import argparse
from dotenv import load_dotenv

import pandas as pd

import sqlalchemy as sqla

from limbless_db import DBHandler, models, categories
from limbless_db.models.Base import Base
from limbless_server import bcrypt

load_dotenv()

if (db_user := os.environ.get("POSTGRES_USER")) is None:
    raise ValueError("POSTGRES_USER environment variable is not set.")

if (db_password := os.environ.get("POSTGRES_PASSWORD")) is None:
    raise ValueError("POSTGRES_PASSWORD environment variable is not set.")

if (db_name := os.environ.get("POSTGRES_DB")) is None:
    raise ValueError("POSTGRES_DB environment variable is not set.")

if (db_port := os.environ.get("POSTGRES_PORT")) is None:
    raise ValueError("POSTGRES_PORT environment variable is not set.")

if (db_host := os.environ.get("POSTGRES_HOST")) is None:
    raise ValueError("POSTGRES_HOST environment variable is not set.")


def titlecase_with_acronyms(val: str) -> str:
    return " ".join([c[0].upper() + c[1:] for c in val.split(" ")])


# Postgres full text search columns
label_search_columns: dict[str, list[str]] = {
    str(models.Project.__tablename__): ["name"],
    str(models.SeqRequest.__tablename__): ["name"],
    str(models.Library.__tablename__): ["name"],
    str(models.Pool.__tablename__): ["name"],
    str(models.Experiment.__tablename__): ["name"],
    str(models.SeqRun.__tablename__): ["experiment_name"],
    str(models.Barcode.__tablename__): ["sequence", "adapter"],
    str(models.IndexKit.__tablename__): ["name"],
    str(models.User.__tablename__): ["email", "last_name", "first_name"],
    str(models.FeatureKit.__tablename__): ["name"],
    str(models.Feature.__tablename__): ["name", "target_name", "target_id"],
}


def add_features_from_kit(db_handler: DBHandler, path: str, feature_type: categories.FeatureType):
    df = pd.read_csv(path, sep="\t", comment="#")
    kit_name = titlecase_with_acronyms(os.path.basename(path).split(".")[0].replace("_", " "))

    if (kit := db_handler.get_feature_kit_by_name(kit_name)) is not None:
        print(f"Feature kit {kit_name} is already present in the DB.")
    else:
        kit = db_handler.create_feature_kit(name=kit_name, type=feature_type)
    
    for _, row in df.iterrows():
        if pd.isnull(row["barcode_id"]):
            print(f"Barcode name is null for row {row}, {kit_name}")
            raise Exception(f"Barcode name is null for row {row}.")
            
        if db_handler.get_feature_from_kit_by_feature_name(feature_kit_id=kit.id, feature_name=str(row["barcode_id"])) is not None:
            print(f"Feature {row['barcode_id']} is already present in the DB.")
            continue
        
        db_handler.create_feature(
            name=str(row["barcode_id"]),
            feature_kit_id=kit.id,
            type=feature_type,
            sequence=row["barcode_sequence"],
            pattern=row["pattern"],
            read=row["read"],
            target_name=row["barcode_target_name"],
            target_id=row["barcode_target_id"],
        )


def add_indices_from_kit(db_handler: DBHandler, path: str):
    df = pd.read_csv(path)
    kit_name = titlecase_with_acronyms(os.path.basename(path).split(".")[0].replace("_", " "))

    num_indices_per_adapter = None
    if "single index" in kit_name.lower():
        num_indices_per_adapter = 4
    elif "dual index" in kit_name.lower():
        num_indices_per_adapter = 2

    assert num_indices_per_adapter is not None
        
    if db_handler.get_index_kit_by_name(kit_name) is not None:
        print(f"Index kit {kit_name} is already present in the DB.")
        return
    
    kit = db_handler.create_index_kit(
        name=kit_name, num_indices_per_adapter=num_indices_per_adapter
    )
    
    for _, row in df.iterrows():
        index_1 = db_handler.create_barcode(
            sequence=row["index_1"],
            adapter=row["index_name"],
            index_kit_id=kit.id,
            barcode_type=categories.BarcodeType.INDEX_1
        )
        index_2, index_3, index_4 = None, None, None
        if "index_2" in row:
            index_2 = db_handler.create_barcode(
                sequence=row["index_2"],
                adapter=row["index_name"],
                index_kit_id=kit.id,
                barcode_type=categories.BarcodeType.INDEX_2
            )
        if "index_3" in row:
            index_3 = db_handler.create_barcode(
                sequence=row["index_3"],
                adapter=row["index_name"],
                index_kit_id=kit.id,
                barcode_type=categories.BarcodeType.INDEX_3
            )
        if "index_4" in row:
            index_4 = db_handler.create_barcode(
                sequence=row["index_4"],
                adapter=row["index_name"],
                index_kit_id=kit.id,
                barcode_type=categories.BarcodeType.INDEX_4
            )

        db_handler.create_adapter(
            name=row["index_name"],
            index_kit_id=kit.id,
            barcode_1_id=index_1.id,
            barcode_2_id=index_2.id if index_2 is not None else None,
            barcode_3_id=index_3.id if index_3 is not None else None,
            barcode_4_id=index_4.id if index_4 is not None else None,
        )


def init_db(create_users: bool):
    db_handler = DBHandler(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)

    # Tables
    db_handler.create_tables()
    q = """
    SELECT * FROM pg_catalog.pg_tables;
    """
    df = pd.read_sql(q, db_handler._engine)

    with open("db_structure.txt", "w") as f:
        for table in Base.metadata.tables.items():
            table_name = table[0]
            if table_name not in df["tablename"].values:
                raise Exception(f"Table {table[0]} is missing from the DB.")

            print(table_name)
            for column in table[1].columns:
                column_name = column.name
                print(f" - {column_name}")
                q = f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}' and column_name='{column_name}';"
                if len(pd.read_sql(q, db_handler._engine)) == 0:
                    raise Exception(f"Column {column_name} is missing from the table {table_name}.")
            
    with open("db_structure.txt", "w") as f:
        for table in Base.metadata.tables.items():
            table_name = table[0]
            f.write(f"{table_name}\n")
            for column in table[1].columns:
                f.write(f" - {column.name}\n")

    # Extensions
    q = """
    SELECT * FROM pg_extension WHERE extname = 'pg_trgm';
    """

    print("Checking if pg_trgm extension is installed.")
    extensions = pd.read_sql(q, db_handler._engine)
    if len(extensions) == 0:
        print("Installing pg_trgm extension.")

        with db_handler._engine.connect() as conn:
            conn.execute(sqla.text('CREATE EXTENSION pg_trgm;COMMIT;'))
    else:
        print("pg_trgm extension is installed.")

    pd.read_sql(q, db_handler._engine)

    # Users
    if create_users:
        print("Creating users.")
        email = "admin@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Admin",
                hashed_password=bcrypt.generate_password_hash("password").decode("utf-8"),
                role=categories.UserRole.ADMIN,
            )
        email = "client@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Client",
                hashed_password=bcrypt.generate_password_hash("password").decode("utf-8"),
                role=categories.UserRole.CLIENT,
            )
        email = "bio@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Bioinformatician",
                hashed_password=bcrypt.generate_password_hash("password").decode("utf-8"),
                role=categories.UserRole.BIOINFORMATICIAN,
            )

        email = "tech@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Technician",
                hashed_password=bcrypt.generate_password_hash("password").decode("utf-8"),
                role=categories.UserRole.TECHNICIAN,
            )

    # Postgres full text search
    for table, columns in label_search_columns.items():
        for column in columns:
            with db_handler._engine.connect() as conn:
                conn.execute(sqla.text(f"""
                    CREATE INDEX IF NOT EXISTS
                        trgm_{table}_{column}_idx
                    ON
                        "{table}"
                    USING
                        gin (lower({column}) gin_trgm_ops);COMMIT;
                """))
    
    with db_handler._engine.connect() as conn:
        conn.execute(sqla.text("""
            CREATE INDEX IF NOT EXISTS
                trgm_user_full_name_idx
            ON
                "lims_user"
            USING
                gin ((first_name || ' ' || last_name) gin_trgm_ops);COMMIT;
        """))

    # Indices
    print("Adding barcodes from known kits.")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_NN_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_NT_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_TN_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_TT_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_TS_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Single_Index_Kit_N_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Single_Index_Kit_T_Set_A.csv")

    # Feature Kits
    print("Adding feature kits.")
    add_features_from_kit(db_handler, "data/feature-kits/CAR_CRISPR_EP_reverse.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/CMO_hastags_florian.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/CMO_multiome_hashtags.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/LCMV_gene_barcode.tsv", categories.FeatureType.GENE_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/LCMV_primer_barcode.tsv", categories.FeatureType.PRIMER_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/LMO_multiome_hashtags.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/LMO_multiome_hashtags_EWS.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/MF_AK_smallCROPSeq.tsv", categories.FeatureType.CUSTOM)
    add_features_from_kit(db_handler, "data/feature-kits/MF_AK_smallCROPSeq_reverse.tsv", categories.FeatureType.CUSTOM)
    add_features_from_kit(db_handler, "data/feature-kits/MultiSeq_LMO.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_PT129_5p_MM10_GRCH38.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_PT129_MM10_GRCH38.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V1_MM10.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V1_MM10_ALT.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V2_MM10.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V2_MM10_GRCH38.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V3_MM10.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V3_MM10_reverse.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/PT_CRISPR_V4_MM10_reverse.tsv", categories.FeatureType.CRISPR_CAPTURE)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqA_Antibody.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqA_Antibody_Multiplex.tsv", categories.FeatureType.CMO)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqB_Antibody.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqC_Antibody.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqC_Antibody_Multiplex.tsv", categories.FeatureType.CMO)

    print("DB initialization finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--create_users", action="store_true")
    parser.add_argument("--add_indices", action="store_true")
    args = parser.parse_args()

    init_db(args.create_users)
    
exit(0)