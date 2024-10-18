import os
import argparse
from dotenv import load_dotenv

import pandas as pd

import sqlalchemy as sa

from limbless_db import DBHandler, models
from limbless_db.models.Base import Base

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
    str(models.IndexKit.__tablename__): ["name"],
    str(models.User.__tablename__): ["email", "last_name", "first_name"],
    str(models.Group.__tablename__): ["name"],
    str(models.FeatureKit.__tablename__): ["name"],
    str(models.Feature.__tablename__): ["name", "target_name", "target_id"],
    str(models.SeqRun.__tablename__): ["experiment_name"],
    str(models.Plate.__tablename__): ["name"],
}


def init_db():
    db_handler = DBHandler(user=db_user, password=db_password, host=db_host, port=db_port, db=db_name)  # type: ignore

    # Tables
    db_handler.create_tables()
    q = """
    SELECT * FROM pg_catalog.pg_tables;
    """
    df = pd.read_sql(q, db_handler._engine)

    os.makedirs("init", exist_ok=True)

    with open(os.path.join("init", "tables.txt"), "w") as f:
        for table in Base.metadata.tables.items():
            table_name = table[0]
            f.write(f"{table_name}\n")
            if table_name not in df["tablename"].values:
                raise Exception(f"Table {table[0]} is missing from the DB.")

            print(table_name)
            for column in table[1].columns:
                column_name = column.name
                f.write(f" - {column_name}\n")
                print(f" - {column_name}")
                q = f"SELECT column_name FROM information_schema.columns WHERE table_name='{table_name}' and column_name='{column_name}';"
                if len(pd.read_sql(q, db_handler._engine)) == 0:
                    raise Exception(f"Column {column_name} is missing from the table {table_name}.")

    # Extensions
    q = """
    SELECT * FROM pg_extension WHERE extname = 'pg_trgm';
    """

    print("Checking if pg_trgm extension is installed.")
    extensions = pd.read_sql(q, db_handler._engine)
    if len(extensions) == 0:
        print("Installing pg_trgm extension.")

        with db_handler._engine.connect() as conn:
            conn.execute(sa.text('CREATE EXTENSION pg_trgm;COMMIT;'))
    else:
        print("pg_trgm extension is installed.")

    pd.read_sql(q, db_handler._engine)

    # Postgres full text search
    for table, columns in label_search_columns.items():
        for column in columns:
            with db_handler._engine.connect() as conn:
                conn.execute(sa.text(f"""
                    CREATE INDEX IF NOT EXISTS
                        trgm_{table}_{column}_idx
                    ON
                        "{table}"
                    USING
                        gin (lower({column}) gin_trgm_ops);COMMIT;
                """))
    
    with db_handler._engine.connect() as conn:
        conn.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS
                trgm_user_full_name_idx
            ON
                "lims_user"
            USING
                gin ((first_name || ' ' || last_name) gin_trgm_ops);COMMIT;
        """))

        conn.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS
                trgm_index_kit_identifier_name_idx
            ON
                "index_kit"
            USING
                gin ((identifier || ' ' || name) gin_trgm_ops);COMMIT;
        """))

    print("DB initialization finished.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    init_db()
    
exit(0)