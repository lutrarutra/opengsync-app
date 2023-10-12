from .core import DBHandler
from .tools import SearchResult
from .index_kits import add_index_kits
from .sample_experiment import create_sample_experiment

db_url = "data/sample_experiment.db"
# db_url = "postgresql://postgres:limbless@localhost/limbless_db"
db_url = "postgresql://postgres:password@127.0.0.1:5432/limbless_db"
# db_path = "data/database.db"

db_handler = DBHandler(db_url)


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

common_organisms = [SearchResult(organism.id, str(organism)) for organism in common_organisms if organism is not None]

common_kits = [
    # db_handler.get_index_kit_by_name("10x Dual Index Kit NN Set A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit NT Set A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit TN Seq A"),
    # db_handler.get_index_kit_by_name("10x Dual Index Kit TT Seq A"),
    # db_handler.get_index_kit_by_name("10x Single Index Kit N Seq A"),
    # db_handler.get_index_kit_by_name("10x Single Index Kit T Seq A"),
]

common_kits = [SearchResult(kit.id, kit.name) for kit in common_kits if kit is not None]
    