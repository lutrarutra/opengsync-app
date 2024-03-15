import os
import argparse
import requests
import pathlib
import glob

import xml.etree.ElementTree as ET

from limbless_db import categories


class Requestor():
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.url = f"http://{self.host}:{self.port}/api/seq_run"

    def post_seq_run(
        self, experiment_name: str, status: categories.ExperimentStatusEnum,
        run_name: str, flowcell_id: str, read_type: categories.ReadTypeEnum,
        rta_version: str, recipe_version: str, side: str,
        flowcell_mode: str, r1_cycles: int, r2_cycles: int, i1_cycles: int, i2_cycles: int,

    ) -> requests.Response:
        response = requests.post(
            self.url + "/create",
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

            }
        )
        return response

    def update_run_status(self, experiment_name: str, status: categories.ExperimentStatusEnum) -> requests.Response:
        response = requests.put(f"{self.url}/{experiment_name}/update_status/{status.id}")
        return response


def parse_run_parameters_xml(run_info_path: str) -> dict:
    tree = ET.parse(run_info_path)
    root = tree.getroot()

    if (experiment_name_el := root.find("ExperimentName")) is not None:
        experiment_name = experiment_name_el.text
    else:
        raise ValueError("ExperimentName not found")

    if (rtype_el := root.find("ReadType")) is not None:
        if rtype_el.text == "PairedEnd":
            read_type = categories.ReadType.PAIRED_END
        elif rtype_el.text == "SingleEnd":
            read_type = categories.ReadType.SINGLE_END
        else:
            raise ValueError(f"Unknown read type: {rtype_el.text}")
    else:
        raise ValueError("ReadType not found")

    if (side_el := root.find("Side")) is not None:
        side = side_el.text
    else:
        raise ValueError("Side not found")

    if (r1_cycles_el := root.find("Read1NumberOfCycles")) is not None:
        r1_cycles = int(r1_cycles_el.text)
    else:
        raise ValueError("Read1NumberOfCycles not found")

    if (r2_cycles_el := root.find("Read2NumberOfCycles")) is not None:
        r2_cycles = int(r2_cycles_el.text)
    else:
        raise ValueError("Read2NumberOfCycles not found")

    if (i1_cycles_el := root.find("IndexRead1NumberOfCycles")) is not None:
        i1_cycles = int(i1_cycles_el.text)
    else:
        raise ValueError("IndexRead1NumberOfCycles not found")

    if (i2_cycles_el := root.find("IndexRead2NumberOfCycles")) is not None:
        i2_cycles = int(i2_cycles_el.text)
    else:
        raise ValueError("IndexRead2NumberOfCycles not found")

    if (flowcell_id_el := root.find("RfidsInfo").find("FlowCellSerialBarcode")) is not None:
        flowcell_id = flowcell_id_el.text
    else:
        raise ValueError("FlowCellSerialBarcode not found")

    if (rta_version_el := root.find("RtaVersion")) is not None:
        rta_version = rta_version_el.text.removeprefix("v")
    else:
        raise ValueError("RTAVersion not found")

    if (recipe_version_el := root.find("RecipeVersion")) is not None:
        recipe_version = recipe_version_el.text.removeprefix("v")
    else:
        raise ValueError("RecipeVersion not found")

    if (flowcell_mode_el := root.find("RfidsInfo").find("FlowCellMode")) is not None:
        flowcell_mode = flowcell_mode_el.text
    else:
        raise ValueError("FlowCellMode not found")
    
    return dict(
        experiment_name=experiment_name,
        read_type=read_type, side=side, r1_cycles=r1_cycles,
        r2_cycles=r2_cycles, i1_cycles=i1_cycles, i2_cycles=i2_cycles,
        flowcell_id=flowcell_id, rta_version=rta_version, recipe_version=recipe_version,
        flowcell_mode=flowcell_mode
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
                response = requestor.update_run_status(experiment_name=experiment_name, status=categories.ExperimentStatus.ARCHIVED)
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
        
        if os.path.exists(os.path.join(run_folder, "RTAComplete.txt")):
            status = categories.ExperimentStatus.FINISHED
        else:
            status = categories.ExperimentStatus.SEQUENCING

        new_run = run_name not in runs_statuses.keys()
        status_change = not new_run and status.id > runs_statuses[run_name]

        if not new_run and not status_change:
            print(f"{run_name} - No changes in status")
            continue
        
        try:
            parsed_data = parse_run_parameters_xml(run_parameters_path)
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
    process_run_folder(args.run_folder, requestor)

exit(0)
