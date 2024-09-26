import os
import argparse
import glob

import pandas as pd

import xml.etree.ElementTree as ET

from limbless_db.categories import RunStatus, ExperimentStatus, ReadType
from limbless_db.core import DBHandler


def parse_run_parameters(run_folder: str) -> dict:
    run_parameters_path = os.path.join(run_folder, "RunParameters.xml")

    tree = ET.parse(os.path.join(run_folder, run_parameters_path))
    root = tree.getroot()

    if (experiment_name_el := root.find("ExperimentName")) is not None:
        experiment_name = experiment_name_el.text
    else:
        raise ValueError("ExperimentName not found")
    
    if (side_el := root.find("Side")) is not None:
        side = side_el.text
    else:
        side = ""
    
    if (rta_version_el := root.find("RtaVersion")) is not None:
        rta_version = rta_version_el.text.removeprefix("v")
    elif (rta_version_el := root.find("RTAVersion")) is not None:
        rta_version = rta_version_el.text.removeprefix("v")
    else:
        raise ValueError("RTAVersion not found")

    if (recipe_version_el := root.find("RecipeVersion")) is not None:
        recipe_version = recipe_version_el.text.removeprefix("v")
    else:
        recipe_version = ""

    if (flowcell_mode_el := root.find("RfidsInfo")) is not None:
        flowcell_mode = flowcell_mode_el.find("FlowCellMode").text
    else:
        flowcell_mode = ""

    if (rfids_info_el := root.find("RfidsInfo")) is not None:
        if (flowcell_id_el := rfids_info_el.find("FlowCellSerialBarcode")) is not None:
            flowcell_id = flowcell_id_el.text

    if (instrument_name_el := root.find("InstrumentName")) is not None:
        instrument_name = instrument_name_el.text
    
    if (read_type_el := root.find("ReadType")) is not None:
        if read_type_el.text == "PairedEnd":
            read_type = ReadType.PAIRED_END
        else:
            read_type = ReadType.SINGLE_END

    r1_cycles, i1_cycles, i2_cycles, r2_cycles = None, None, None, None
    _reads = run_info.reads()
    for i in range(0, len(_reads)):
        read = _reads[i]
        read_number = read.number()
        if read_number == 1:
            if read.is_index():
                raise Exception("r1 is index-read")
            r1_cycles = read.total_cycles()
        elif read_number == 2:
            if not read.is_index():
                raise Exception("i1 is not index-read")
            i1_cycles = read.total_cycles()
        elif read_number == 3:
            if not read.is_index():
                raise Exception("i2 is not index-read")
            i2_cycles = read.total_cycles()
        elif read_number == 4:
            if read.is_index():
                raise Exception("r2 is index-read")
            r2_cycles = read.total_cycles()

    try:
        metrics = interop.read(run_folder)
        metrics_df = pd.DataFrame(interop.summary(metrics))
        cluster_count_m = float(metrics_df["Cluster Count"].values[0] / 1_000_000)
        cluster_count_m_pf = float(metrics_df["Cluster Count Pf"].values[0] / 1_000_000)
        error_rate = float(metrics_df["Error Rate"].values[0]) if "Error Rate" in metrics_df.columns else None
        first_cycle_intensity = float(metrics_df["First Cycle Intensity"].values[0])
        percent_aligned = float(metrics_df["% Aligned"].values[0])
        percent_q30 = float(metrics_df["% >= Q30"].values[0])
        percent_occupied = float(metrics_df["% Occupied"].values[0])
        projected_yield = float(metrics_df["Projected Yield G"].values[0])
        reads_m = float(metrics_df["Reads"].values[0] / 1_000_000)
        reads_m_pf = float(metrics_df["Reads Pf"].values[0] / 1_000_000)
        yield_g = float(metrics_df["Yield G"].values[0])
    except Exception:
        cluster_count_m = None
        cluster_count_m_pf = None
        error_rate = None
        first_cycle_intensity = None
        percent_aligned = None
        percent_q30 = None
        percent_occupied = None
        projected_yield = None
        reads_m = None
        reads_m_pf = None
        yield_g = None

    return dict(
        experiment_name=experiment_name,
        read_type=read_type, side=side, r1_cycles=r1_cycles,
        r2_cycles=r2_cycles, i1_cycles=i1_cycles, i2_cycles=i2_cycles,
        flowcell_id=flowcell_id, rta_version=rta_version, recipe_version=recipe_version,
        flowcell_mode=flowcell_mode, cluster_count_m=cluster_count_m, cluster_count_m_pf=cluster_count_m_pf,
        error_rate=error_rate, first_cycle_intensity=first_cycle_intensity, percent_aligned=percent_aligned,
        percent_q30=percent_q30, percent_occupied=percent_occupied, projected_yield=projected_yield,
        reads_m=reads_m, reads_m_pf=reads_m_pf, yield_g=yield_g, instrument_name=instrument_name
    )


def process_run_folder(illumina_run_folder: str, db: DBHandler) -> None:
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
        
        parsed_data = parse_run_parameters(run_folder)
        
        experiment_name = parsed_data["experiment_name"]
        print(f"Processing: {experiment_name} ({run_name})")

        if (run := active_runs.get(experiment_name)) is not None:
            if run.status == status:
                print("Up to date..")
                continue
            
            run.status_id = status.id
            run.instrument_name = parsed_data["instrument_name"]
            run.flowcell_id = parsed_data["flowcell_id"]
            run.rta_version = parsed_data["rta_version"]
            run.recipe_version = parsed_data["recipe_version"]
            run.side = parsed_data["side"]
            run.flowcell_mode = parsed_data["flowcell_mode"]
            run.read_type_id = parsed_data["read_type"].id
            run.r1_cycles = parsed_data["r1_cycles"]
            run.r2_cycles = parsed_data["r2_cycles"]
            run.i1_cycles = parsed_data["i1_cycles"]
            run.i2_cycles = parsed_data["i2_cycles"]
            run.cluster_count_m = parsed_data["cluster_count_m"]
            run.cluster_count_m_pf = parsed_data["cluster_count_m_pf"]
            run.error_rate = parsed_data["error_rate"]
            run.first_cycle_intensity = parsed_data["first_cycle_intensity"]
            run.percent_aligned = parsed_data["percent_aligned"]
            run.percent_q30 = parsed_data["percent_q30"]
            run.percent_occupied = parsed_data["percent_occupied"]
            run.projected_yield = parsed_data["projected_yield"]
            run.reads_m = parsed_data["reads_m"]
            run.reads_m_pf = parsed_data["reads_m_pf"]
            run.yield_g = parsed_data["yield_g"]

            run = db.update_seq_run(run)
            active_runs[experiment_name] = run
            print("Updated!")
        else:
            run = db.create_seq_run(
                experiment_name=experiment_name,
                status=status,
                run_folder=run_name,
                instrument_name=parsed_data["instrument_name"],
                flowcell_id=parsed_data["flowcell_id"],
                rta_version=parsed_data["rta_version"],
                recipe_version=parsed_data.get("recipe_version"),
                side=parsed_data.get("side"),
                flowcell_mode=parsed_data.get("flowcell_mode"),
                read_type=parsed_data["read_type"],
                r1_cycles=parsed_data.get("r1_cycles"),
                r2_cycles=parsed_data.get("r2_cycles"),
                i1_cycles=parsed_data.get("i1_cycles"),
                i2_cycles=parsed_data.get("i2_cycles"),
                cluster_count_m=parsed_data.get("cluster_count_m"),
                cluster_count_m_pf=parsed_data.get("cluster_count_m_pf"),
                error_rate=parsed_data.get("error_rate"),
                first_cycle_intensity=parsed_data.get("first_cycle_intensity"),
                percent_aligned=parsed_data.get("percent_aligned"),
                percent_q30=parsed_data.get("percent_q30"),
                percent_occupied=parsed_data.get("percent_occupied"),
                projected_yield=parsed_data.get("projected_yield"),
                reads_m=parsed_data.get("reads_m"),
                reads_m_pf=parsed_data.get("reads_m_pf"),
                yield_g=parsed_data.get("yield_g")
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