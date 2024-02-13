import os

from limbless_db import DBHandler, SearchResult

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


db_handler = DBHandler(f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")
db_handler.create_tables()

common_organisms = [
    db_handler.get_organism(9606),
    db_handler.get_organism(10090),
    db_handler.get_organism(562),
    db_handler.get_organism(4932),
    db_handler.get_organism(3702),
    db_handler.get_organism(7227),
    db_handler.get_organism(6239),
    db_handler.get_organism(7955),
    db_handler.get_organism(1423),
    db_handler.get_organism(1773),
    db_handler.get_organism(5833),
]

common_organisms = [
    organism for organism in common_organisms if organism is not None
]

common_kits = [
    # db_handler.get_index_kit_by_name("10x Dual Index Kit NN Set A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit NT Set A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit TN Seq A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit TT Seq A"),
    # db_handler.get_index_kit_by_name("10x Single Index Kit N Seq A"),
    # db_handler.get_index_kit_by_name("10x Single Index Kit T Seq A"),
]

common_kits = [SearchResult(kit.id, kit.name) for kit in common_kits if kit is not None]
    