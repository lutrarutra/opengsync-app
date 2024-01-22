import os
import sys
import argparse
from dotenv import load_dotenv

from loguru import logger
import pandas as pd

from sqlmodel import SQLModel
import sqlalchemy as sqla

import limbless.models as models
import limbless.categories as categories
from limbless.core import DBHandler

load_dotenv()

fmt = """{level} @ {time:YYYY-MM-DD HH:mm:ss} ({file}:{line} in {function}):
>   {message}"""

logger.remove()
date = "{time:YYYY-MM-DD}"

logger.add(
    f"logs/{date}_startup.log", format=fmt, level="INFO",
    colorize=False, rotation="1 day"
)

logger.add(
    sys.stdout, colorize=True,
    format=fmt, level="INFO"
)

# Postgres full text search columns
label_search_columns: dict[str, list[str]] = {
    str(models.Project.__tablename__): ["name"],
    str(models.SeqRequest.__tablename__): ["name"],
    str(models.Library.__tablename__): ["name"],
    str(models.Pool.__tablename__): ["name"],
    str(models.Organism.__tablename__): ["scientific_name", "common_name"],
    str(models.Barcode.__tablename__): ["sequence", "adapter"],
    str(models.IndexKit.__tablename__): ["name"],
    str(models.User.__tablename__): ["email", "last_name", "first_name"],
    str(models.FeatureKit.__tablename__): ["name"],
    str(models.Feature.__tablename__): ["name", "target_name", "target_id"],
}

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


def add_features_from_kit(db_handler: DBHandler, path: str, feature_type: categories.FeatureType):
    df = pd.read_csv(path, sep="\t", comment="#")
    kit_name = os.path.basename(path).split(".")[0].replace("_", " ").title()

    if db_handler.get_feature_kit_by_name(kit_name) is not None:
        logger.info(f"Feature kit {kit_name} is already present in the DB.")
        return
    
    if db_handler.get_feature_kit_by_name(kit_name) is not None:
        logger.info(f"Feature kit {kit_name} is already present in the DB.")
        return
    
    kit = db_handler.create_feature_kit(name=kit_name, type=feature_type)
    
    for _, row in df.iterrows():
        if pd.isnull(row["barcode_id"]):
            logger.error(f"Barcode name is null for row {row}, {kit_name}")
            raise Exception(f"Barcode name is null for row {row}.")
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
    kit_name = os.path.basename(path).split(".")[0].replace("_", " ").title()

    num_indices_per_adapter = None
    if "single index" in kit_name.lower():
        num_indices_per_adapter = 4
    elif "dual index" in kit_name.lower():
        num_indices_per_adapter = 2

    assert num_indices_per_adapter is not None
        
    if db_handler.get_index_kit_by_name(kit_name) is not None:
        logger.info(f"Index kit {kit_name} is already present in the DB.")
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
    db_handler = DBHandler(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")

    # Tables
    # tables = pd.Series(list(SQLModel.metadata.tables.keys()))
    db_handler.init_database()
    q = """
    SELECT * FROM pg_catalog.pg_tables;
    """
    df = pd.read_sql(q, db_handler._engine)

    with open("db_structure.txt", "w") as f:
        for table in SQLModel.metadata.tables.items():
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
        for table in SQLModel.metadata.tables.items():
            table_name = table[0]
            f.write(f"{table_name}\n")
            for column in table[1].columns:
                f.write(f" - {column.name}\n")

    # Extensions
    q = """
    SELECT * FROM pg_extension WHERE extname = 'pg_trgm';
    """

    logger.info("Checking if pg_trgm extension is installed.")
    extensions = pd.read_sql(q, db_handler._engine)
    if len(extensions) == 0:
        logger.info("Installing pg_trgm extension.")

        with db_handler._engine.connect() as conn:
            conn.execute(sqla.text('CREATE EXTENSION pg_trgm;COMMIT;'))
    else:
        logger.info("pg_trgm extension is installed.")

    pd.read_sql(q, db_handler._engine)

    # Users
    if create_users:
        logger.info("Creating users.")
        email = "admin@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Admin",
                password="password",
                role=categories.UserRole.ADMIN,
            )
        email = "client@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Client",
                password="password",
                role=categories.UserRole.CLIENT,
            )
        email = "bio@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Bioinformatician",
                password="password",
                role=categories.UserRole.BIOINFORMATICIAN,
            )

        email = "tech@email.com"
        if not db_handler.get_user_by_email(email):
            db_handler.create_user(
                email=email,
                first_name="CeMM",
                last_name="Technician",
                password="password",
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

    if db_handler.get_organism(10090) is None:
        db_handler.create_organism(
            tax_id=10090,
            scientific_name="Mus musculus",
            common_name="House mouse",
            category=categories.OrganismCategory.EUKARYOTA,
        )

    if db_handler.get_organism(9606) is None:
        db_handler.create_organism(
            tax_id=9606,
            scientific_name="Homo sapiens",
            common_name="Human",
            category=categories.OrganismCategory.EUKARYOTA,
        )

    if db_handler.get_organism(4932) is None:
        db_handler.create_organism(
            tax_id=4932,
            scientific_name="Saccharomyces cerevisiae",
            common_name="Baker's yeast",
            category=categories.OrganismCategory.EUKARYOTA,
        )

    if db_handler.get_organism(1773) is None:
        db_handler.create_organism(
            tax_id=1773,
            scientific_name="Mycobacterium tuberculosis",
            common_name=None,
            category=categories.OrganismCategory.BACTERIA,
        )

    if db_handler.get_organism(5833) is None:
        db_handler.create_organism(
            tax_id=5833,
            scientific_name="Plasmodium falciparum",
            common_name=None,
            category=categories.OrganismCategory.EUKARYOTA,
        )

    # Indices
    logger.info("Adding barcodes from known kits.")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_NN_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_NT_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_TN_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Dual_Index_Kit_TT_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Single_Index_Kit_N_Set_A.csv")
    add_indices_from_kit(db_handler, "data/index-kits/10x_kits/Single_Index_Kit_T_Set_A.csv")

    # Feature Kits
    logger.info("Adding feature kits.")
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
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqA_Antibody_Multiplex.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqB_Antibody.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqC_Antibody.tsv", categories.FeatureType.ANTIBODY)
    add_features_from_kit(db_handler, "data/feature-kits/TotalSeqC_Antibody_Multiplex.tsv", categories.FeatureType.ANTIBODY)

    logger.info("DB initialization finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--create_users", action="store_true")
    parser.add_argument("--add_indices", action="store_true")
    parser.add_argument("--db_host", default=None)
    parser.add_argument("--db_port", default=None)
    args = parser.parse_args()
    
    if args.db_host is not None:
        db_host = args.db_host
    if args.db_port is not None:
        db_port = args.db_port

    init_db(args.create_users)
    
exit(0)