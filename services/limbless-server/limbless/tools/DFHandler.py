import pandas as pd

from ..core.DBHandler import DBHandler


# TODO: testing
def experiment_to_df(db_handler: DBHandler, experiment_id: int):
    experiment_data = db_handler.get_experiment_data(1, unraveled=True)
    data = []
    for run, library, sample in experiment_data:
        data.append(dict(
            sample_name=sample.name,
            organism=sample.organism,
            sample_id=sample.id,
            index1=sample.index1,
            index2=sample.index2,
            project_id=sample.project_id,
            library_name=library.name,
            library_type=library.type,
            run_lane=run.lane,
            r1_cycles=run.r1_cycles,
            r2_cycles=run.r2_cycles,
            i1_cycles=run.i1_cycles,
            i2_cycles=run.i2_cycles
        ))

    return pd.DataFrame(data)
