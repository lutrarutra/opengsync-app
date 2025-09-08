from typing import Optional
import os
import glob
from pathlib import Path

import pandas as pd
import interop
from xml.dom.minidom import parse
from dataclasses import dataclass

from opengsync_db.categories import RunStatus, ExperimentStatus, ReadType, LibraryStatus, PoolStatus
from opengsync_db.core import DBHandler
from opengsync_db import units

from . import logger


def get_dom_value(dom, tag_name: str) -> str | None:
    if len(matches := dom.getElementsByTagName(tag_name)) == 0:
        return None
    if len(matches) > 1:
        raise ValueError(f"Multiple matches for tag: {tag_name}")
    if (fc := matches[0].firstChild) is None:
        return None
    return fc.nodeValue


def parse_read_cycles(run_info) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    r1_cycles, i1_cycles, i2_cycles, r2_cycles = None, None, None, None
    _reads = run_info.reads()

    indices = []
    reads = []

    for i in range(0, len(_reads)):
        read = _reads[i]
        if read.is_index():
            indices.append(read)
        else:
            reads.append(read)

    r1_cycles = reads[0].total_cycles()
    r2_cycles = reads[1].total_cycles() if len(reads) > 1 else None
    i1_cycles = indices[0].total_cycles() if len(indices) > 0 else None
    i2_cycles = indices[1].total_cycles() if len(indices) > 1 else None

    return r1_cycles, i1_cycles, i2_cycles, r2_cycles


def parse_run_folder(run_folder: Path) -> dict:
    run_info = interop.py_interop_run.info()     # type: ignore
    run_info.read(run_folder.as_posix())
    
    flowcell_id = run_info.flowcell().barcode()
    instrument = run_info.instrument_name()
    
    if run_info.is_paired_end():
        read_type = ReadType.PAIRED_END
    else:
        read_type = ReadType.SINGLE_END
    
    r1_cycles, i1_cycles, i2_cycles, r2_cycles = parse_read_cycles(run_info)

    run_params_dom = parse(os.path.join(run_folder, "RunParameters.xml"))
    experiment_name = get_dom_value(run_params_dom, "ExperimentName")
    rta_version = get_dom_value(run_params_dom, "RTAVersion")
    run_id = get_dom_value(run_params_dom, "RunId")

    return {
        "experiment_name": experiment_name,
        "r1_cycles": r1_cycles,
        "i1_cycles": i1_cycles,
        "i2_cycles": i2_cycles,
        "r2_cycles": r2_cycles,
        "flowcell_id": flowcell_id,
        "instrument": instrument,
        "rta_version": rta_version,
        "run_id": run_id,
        "read_type": read_type
    }


@dataclass
class UnitParse:
    label: str
    unit: units.Unit = units.count
    rename: str | None = None


def parse_quantitities(run_folder: Path, quantities: list[UnitParse]) -> dict[str, units.Quantity]:
    metrics = interop.read(run_folder.as_posix())
    df = pd.DataFrame(interop.summary(metrics))
    df.columns = [(
        str(col)
        .replace(" >", ">")
        .replace(" <", "<")
        .replace(" =", "=")
        .replace("= ", "=")
        .replace(" ", "_")
        .replace("%", "pct")
        .lower()
    ) for col in df.columns]

    res = {}

    if len(df) > 1:
        logger.warning(f"{run_folder}: Expected 1 row in metrics DataFrame, found {len(df)}. Using the first row.")
    elif len(df) == 0:
        logger.error(f"{run_folder}: Metrics DataFrame is empty. Cannot parse quantities.")
        return {}

    variables = df.iloc[0].to_dict()

    def parse_quantity(name: str, unit: units.Unit, new_name: str):
        if name in variables.keys():
            res[new_name] = variables.pop(name) * unit

    for conv in quantities:
        parse_quantity(
            name=conv.label,
            unit=conv.unit,
            new_name=conv.rename or conv.label
        )

    for name, value in variables.items():
        res[name] = value * units.count

    return res


def parse_metrics(run_folder: Path) -> dict[str, units.Quantity]:
    quantities = parse_quantitities(
        run_folder,
        [
            UnitParse("cluster_count", units.count),
            UnitParse("cluster_count_pf", units.count),
            UnitParse("pct_aligned", units.percent),
            UnitParse("pct>=q30", units.percent),
            UnitParse("pct_occupied", units.percent),
            UnitParse("projected_yield_g", units.b_count, "projected_yield"),
            UnitParse("reads", units.read),
            UnitParse("reads_pf", units.read),
            UnitParse("yield_g", units.b_count, "yield"),
        ]
    )
    return quantities


def process_run_folder(illumina_run_folder: Path, db: DBHandler):
    logger.info(f"Processing run folder: {illumina_run_folder}")
    
    active_runs, _ = db.seq_runs.find(
        status_in=[RunStatus.FINISHED, RunStatus.RUNNING],
        limit=None
    )

    active_runs = dict([(run.experiment_name, run) for run in active_runs])

    for run in active_runs.values():
        if not os.path.exists(os.path.join(illumina_run_folder, run.run_folder)):
            run.status = RunStatus.ARCHIVED
            if run.experiment is not None:
                run.experiment.status = ExperimentStatus.ARCHIVED
                for pool in run.experiment.pools:
                    pool.status = PoolStatus.SEQUENCED
                    for library in pool.libraries:
                        library.status = LibraryStatus.SEQUENCED
            db.seq_runs.update(run)
            active_runs[run.experiment_name] = run
            logger.info(f"Archived: {run.experiment_name} ({run.run_folder})")
    
    for run_parameters_path in glob.glob(os.path.join(illumina_run_folder, "*", "RunParameters.xml")):
        run_folder = Path(os.path.dirname(run_parameters_path))
        run_name = run_folder.name
        
        if os.path.exists(os.path.join(run_folder, "RTAComplete.txt")):
            status = RunStatus.FINISHED
        else:
            status = RunStatus.RUNNING
        
        parsed_data = parse_run_folder(run_folder)
        
        experiment_name = parsed_data["experiment_name"]
        logger.info(f"Processing {experiment_name} ({run_name}):")

        if (run := active_runs.get(experiment_name)) is not None:
            if run.run_folder != run_name:
                logger.info(f"WARNING: Run folder name mismatch: {run.run_folder} != {run_name}.")
                if status > run.status:
                    logger.info(f"Updating run folder name to {run_name}.")
                    run.run_folder = run_name
                    db.seq_runs.update(run)
                    parsed_data = parse_run_folder(run_folder)
                else:
                    logger.info("Skipping update due to lower status.")
                    continue
                
            if run.status == status:
                logger.info("Up to date!")
                continue
            
            if run.status == RunStatus.FINISHED:
                if run.experiment is not None:
                    run.experiment.status = ExperimentStatus.FINISHED
                    for pool in run.experiment.pools:
                        pool.status = PoolStatus.SEQUENCED
                        for library in pool.libraries:
                            library.status = LibraryStatus.SEQUENCED
            
            # This should not happen
            if run.status == RunStatus.ARCHIVED:
                continue
            
            metrics = parse_metrics(run_folder)
            
            run.status = status
            run.instrument_name = parsed_data["instrument"]
            run.flowcell_id = parsed_data["flowcell_id"]
            run.rta_version = parsed_data["rta_version"]
            run.read_type = parsed_data["read_type"]
            run.r1_cycles = parsed_data["r1_cycles"]
            run.r2_cycles = parsed_data["r2_cycles"]
            run.i1_cycles = parsed_data["i1_cycles"]
            run.i2_cycles = parsed_data["i2_cycles"]

            for key, value in metrics.items():
                run.set_quantity(key, value)

            db.seq_runs.update(run)
            active_runs[experiment_name] = run
            logger.info("Updated!")
        else:
            metrics = parse_metrics(run_folder)

            # If for some reason the run is Archived while the data is still in the run folder
            if (seq_run := db.seq_runs.get(experiment_name=experiment_name)) is not None:
                seq_run.status = status
                db.seq_runs.update(seq_run)
                continue
                    
            run = db.seq_runs.create(
                experiment_name=experiment_name,
                status=status,
                run_folder=run_name,
                instrument_name=parsed_data["instrument"],
                flowcell_id=parsed_data["flowcell_id"],
                rta_version=parsed_data["rta_version"],
                read_type=parsed_data["read_type"],
                r1_cycles=parsed_data.get("r1_cycles"),
                r2_cycles=parsed_data.get("r2_cycles"),
                i1_cycles=parsed_data.get("i1_cycles"),
                i2_cycles=parsed_data.get("i2_cycles"),
                quantities=metrics,
            )

            if run.status == RunStatus.FINISHED:
                if run.experiment is not None:
                    run.experiment.status = ExperimentStatus.FINISHED
                    for pool in run.experiment.pools:
                        pool.status = PoolStatus.SEQUENCED
                        for library in pool.libraries:
                            library.status = LibraryStatus.SEQUENCED
            elif run.status == RunStatus.RUNNING:
                if run.experiment is not None:
                    run.experiment.status = ExperimentStatus.SEQUENCING
            
            db.seq_runs.update(run)

            active_runs[experiment_name] = run
            logger.info("Added!")
