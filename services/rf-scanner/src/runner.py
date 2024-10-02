from typing import Optional
import os
import argparse
import glob
import datetime

import interop
from xml.dom.minidom import parse

from limbless_db.categories import RunStatus, ExperimentStatus, ReadType
from limbless_db.core import DBHandler


def get_dom_value(dom, tag_name: str) -> str | None:
    if (fc := dom.getElementsByTagName(tag_name)[0].firstChild) is None:
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


def parse_run_folder(run_folder: str) -> dict:
    run_info = interop.py_interop_run.info()     # type: ignore
    run_info.read(run_folder)
    
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


def process_run_folder(illumina_run_folder: str, db: DBHandler):
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} Processing run folder: {illumina_run_folder}")
    active_runs, _ = db.get_seq_runs(
        status_in=[RunStatus.FINISHED, RunStatus.RUNNING],
        limit=None
    )

    active_runs = dict([(run.experiment_name, run) for run in active_runs])

    for run in active_runs.values():
        if not os.path.exists(os.path.join(illumina_run_folder, run.run_folder)):
            run.status_id = RunStatus.ARCHIVED.id
            run = db.update_seq_run(run)
            active_runs[run.experiment_name] = run
            print(f"Archived: {run.experiment_name} ({run.run_folder})")
            if (experiment := db.get_experiment(name=run.experiment_name)) is not None:
                experiment.status_id = ExperimentStatus.ARCHIVED.id
                experiment = db.update_experiment(experiment)
    
    for run_parameters_path in glob.glob(os.path.join(illumina_run_folder, "*", "RunParameters.xml")):
        run_folder = os.path.dirname(run_parameters_path)
        run_name = os.path.basename(run_folder)
        
        if os.path.exists(os.path.join(run_folder, "RTAComplete.txt")):
            status = RunStatus.FINISHED
        else:
            status = RunStatus.RUNNING
        
        parsed_data = parse_run_folder(run_folder)
        
        experiment_name = parsed_data["experiment_name"]
        print(f"Processing: {experiment_name} ({run_name}): ", end="")

        if (run := active_runs.get(experiment_name)) is not None:
            if run.status == status:
                print("Up to date!")
                continue
            
            run.status_id = status.id
            run.instrument_name = parsed_data["instrument"]
            run.flowcell_id = parsed_data["flowcell_id"]
            run.rta_version = parsed_data["rta_version"]
            run.read_type_id = parsed_data["read_type"].id
            run.r1_cycles = parsed_data["r1_cycles"]
            run.r2_cycles = parsed_data["r2_cycles"]
            run.i1_cycles = parsed_data["i1_cycles"]
            run.i2_cycles = parsed_data["i2_cycles"]

            run = db.update_seq_run(run)
            active_runs[experiment_name] = run
            print("Updated!")
        else:
            run = db.create_seq_run(
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
            )
            active_runs[experiment_name] = run
            print("Added!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_folder", type=str)
    parser.add_argument("user", type=str)
    parser.add_argument("password", type=str)
    parser.add_argument("host", type=str)
    parser.add_argument("db", type=str, default="limbless_db")
    parser.add_argument("port", type=int, default=5432)
    
    args = parser.parse_args()

    db = DBHandler(
        user=args.user,
        password=args.password,
        host=args.host,
        db=args.db,
        port=args.port
    )

    if not os.path.exists(args.run_folder):
        raise FileNotFoundError(f"Run folder not found: {args.run_folder}")
        
    process_run_folder(args.run_folder, db)

exit(0)