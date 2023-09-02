from .core import DBHandler

# db_handler = DBHandler("data/database.db", load_sample_data=False)
db_handler = DBHandler("data/sample_experiment.db", load_sample_data=True)

common_organisms = [
    db_handler.get_organism(9606),
    db_handler.get_organism(10090),
    db_handler.get_organism(562),
    db_handler.get_organism(4932),
    db_handler.get_organism(3702),
    db_handler.get_organism(7227),
    db_handler.get_organism(6239),
    db_handler.get_organism(7955),
    db_handler.get_organism(6239),
    db_handler.get_organism(1423),
    db_handler.get_organism(6239),
    db_handler.get_organism(1773),
    db_handler.get_organism(5833),
]

common_organisms = [org for org in common_organisms if org is not None]