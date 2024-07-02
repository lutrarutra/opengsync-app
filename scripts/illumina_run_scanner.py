import os
import argparse
import requests
import pathlib
import glob
import interop

import pandas as pd

import xml.etree.ElementTree as ET

from limbless_db import categories


class Requestor():
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.url = f"http://{self.host}:{self.port}"

    def check_connection(self) -> bool:
        try:
            response = requests.get(self.url + "/status")
        except requests.exceptions.ConnectionError:
            return False
        return response.status_code == 200

    def post_seq_run(
        self, experiment_name: str, status: categories.RunStatusEnum,
        run_name: str, flowcell_id: str, read_type: categories.ReadTypeEnum,
        instrument_name: str, rta_version: str, recipe_version: str, side: str,
        flowcell_mode: str, r1_cycles: int, r2_cycles: int, i1_cycles: int, i2_cycles: int,
        cluster_count_m: float, cluster_count_m_pf: float, error_rate: float,
        first_cycle_intensity: float, percent_aligned: float, percent_q30: float,
        percent_occupied: float, projected_yield: float, reads_m: float, reads_m_pf: float,
        yield_g: float
    ) -> requests.Response:
        response = requests.post(
            self.url + "/api/seq_run/create",
            data={
                "experiment_name": experiment_name,
                "status": status.id,
                "run_folder": run_name,
                "flowcell_id": flowcell_id,
                "read_type": read_type.id,
                "rta_version": rta_version,
                "recipe_version": recipe_version,
                "side": side,
                "flowcell_mode": flowcell_mode,
                "r1_cycles": r1_cycles,
                "r2_cycles": r2_cycles,
                "i1_cycles": i1_cycles,
                "i2_cycles": i2_cycles,
                "cluster_count_m": cluster_count_m,
                "cluster_count_m_pf": cluster_count_m_pf,
                "error_rate": error_rate,
                "first_cycle_intensity": first_cycle_intensity,
                "percent_aligned": percent_aligned,
                "percent_q30": percent_q30,
                "percent_occupied": percent_occupied,
                "projected_yield": projected_yield,
                "reads_m": reads_m,
                "reads_m_pf": reads_m_pf,
                "yield_g": yield_g,
                "instrument_name": instrument_name
            }
        )
        return response

    def update_run_status(self, experiment_name: str, status: categories.RunStatusEnum) -> requests.Response:
        response = requests.put(f"{self.url}/api/seq_run/{experiment_name}/update_status/{status.id}")
        return response


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

    run_info = interop.py_interop_run.info()     # type: ignore
    run_info.read(run_folder)
    
    flowcell_id = run_info.flowcell().barcode()
    instrument_name = run_info.instrument_name()
    
    if run_info.is_paired_end():
        read_type = categories.ReadType.PAIRED_END
    else:
        read_type = categories.ReadType.SINGLE_END

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
        cluster_count_m = metrics_df["Cluster Count"].values[0] / 1_000_000
        cluster_count_m_pf = metrics_df["Cluster Count Pf"].values[0] / 1_000_000
        error_rate = metrics_df["Error Rate"].values[0] if "Error Rate" in metrics_df.columns else None
        first_cycle_intensity = metrics_df["First Cycle Intensity"].values[0]
        percent_aligned = metrics_df["% Aligned"].values[0]
        percent_q30 = metrics_df["% >= Q30"].values[0]
        percent_occupied = metrics_df["% Occupied"].values[0]
        projected_yield = metrics_df["Projected Yield G"].values[0]
        reads_m = metrics_df["Reads"].values[0] / 1_000_000
        reads_m_pf = metrics_df["Reads Pf"].values[0] / 1_000_000
        yield_g = metrics_df["Yield G"].values[0]
    except Exception:
        print("Could not parse metrics...")
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


def process_run_folder(illumina_run_folder: str, requestor: Requestor) -> None:
    runs = glob.glob(os.path.join(illumina_run_folder, "*", "RunParameters.xml"))
    completed_runs_path = os.path.join(illumina_run_folder, ".runs")

    if not os.path.exists(completed_runs_path):
        pathlib.Path(completed_runs_path).touch()

    runs_statuses = {}
    
    archived = []
    scanned_runs: list[tuple[str, str, int]] = []
    with open(completed_runs_path, "r") as f:
        while (line := f.readline()):
            line = line.strip()
            run = line.split("\t")[0]
            experiment_name = line.split("\t")[1]
            status = line.split("\t")[2]
            runs_statuses[run] = int(status)
            scanned_runs.append((run, experiment_name, int(status)))
            
            run_parameters_path = os.path.join(illumina_run_folder, run, "RunParameters.xml")
            if not os.path.exists(run_parameters_path) and experiment_name not in archived:
                response = requestor.update_run_status(experiment_name=experiment_name, status=categories.RunStatus.ARCHIVED)
                print(f"{run} - HTTP[{response.status_code}]: Archived.")
                archived.append(experiment_name)

    with open(completed_runs_path, "w") as f:
        for run, experiment_name, status in scanned_runs:
            if experiment_name in archived:
                continue
            f.write(f"{run}\t{experiment_name}\t{status}\n")
        
    for run_parameters_path in runs:
        run_folder = os.path.dirname(run_parameters_path)
        run_name = os.path.basename(run_folder)
        print(f"Processing: {run_name}")
        
        if os.path.exists(os.path.join(run_folder, "RTAComplete.txt")):
            status = categories.RunStatus.FINISHED
        else:
            status = categories.RunStatus.RUNNING

        new_run = run_name not in runs_statuses.keys()
        status_change = not new_run and status.id > runs_statuses[run_name]

        if not new_run and not status_change:
            print(f"{run_name} - No changes in status")
            continue
        
        try:
            parsed_data = parse_run_parameters(run_folder)
        except Exception as e:
            print(f"{run_name} - ERROR: {e}")
            continue
        
        experiment_name = parsed_data["experiment_name"]

        if status_change:
            response = requestor.update_run_status(experiment_name=experiment_name, status=status)
        else:
            response = requestor.post_seq_run(run_name=run_name, status=status, **parsed_data)

        if response.status_code == 200:
            if new_run:
                print(f"{run_name} - HTTP[{response.status_code}]: Run added.")
            elif status_change:
                print(f"{run_name} - HTTP[{response.status_code}]: Status {runs_statuses[run_name]} -> {status.id}")
            with open(completed_runs_path, "a") as f:
                f.write(f"{run_name}\t{experiment_name}\t{status.id}\n")
        elif response.status_code == 201:
            print(f"{run_name} - HTTP[{response.status_code}]: Run already in DB.")
            with open(completed_runs_path, "a") as f:
                f.write(f"{run_name}\t{experiment_name}\t{0}\n")
        else:
            print(f"{run_name} - HTTP[{response.status_code}]: {response.content}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_folder", type=str)
    parser.add_argument("host", type=str)
    parser.add_argument("port", type=int)

    args = parser.parse_args()

    if not os.path.exists(args.run_folder):
        raise FileNotFoundError(f"Run folder not found: {args.run_folder}")

    requestor = Requestor(args.host, args.port)
    if not requestor.check_connection():
        print(f"Host '{requestor.url}' not available.")
        exit(1)
        
    process_run_folder(args.run_folder, requestor)

exit(0)
