import os
import datetime
from typing import Optional, Any, OrderedDict
from uuid import uuid4
from dataclasses import dataclass

import pickle
import pandas as pd

from .. import config_cache, logger
from .HTMXFlaskForm import HTMXFlaskForm
import shutil


@dataclass
class StepFile():
    args: dict[str, Any]
    metadata: dict[str, Any]
    tables: dict[str, pd.DataFrame]


class MultiStepForm(HTMXFlaskForm):
    _step_name: str = None  # type: ignore
    _workflow_name: str = None  # type: ignore

    def __init__(self, workflow: str, uuid: str | None, formdata: dict, step_name: str, step_args: dict, previous_form: Optional["MultiStepForm"] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = str(uuid4())

        self.step_name = step_name
        self.step_args = step_args
        self.uuid = uuid
        self.workflow = workflow
        self.__path = os.path.join("uploads", workflow, f"{uuid}.msf")
        if not os.path.exists(os.path.dirname(self.__path)):
            os.mkdir(os.path.dirname(self.__path))

        self.__header: dict[str, Any]
        self.__steps: dict[str, StepFile]

        if previous_form is not None:
            self.__header = previous_form.__header
            self.__steps = previous_form.__steps
        elif os.path.exists(self.__path):
            self.__read()
        else:
            self.__header = {
                "workflow": self.workflow,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self.__steps = OrderedDict()

        if previous_form is not None:
            self.__current_step = StepFile(
                args=self.step_args,
                metadata=previous_form.metadata,
                tables=previous_form.tables
            )
        elif len(self.__steps) == 0:
            self.__current_step = StepFile(
                args=self.step_args,
                metadata={},
                tables={}
            )
        else:
            last_step = list(self.__steps.values())[-1]
            self.__current_step = StepFile(
                args=self.step_args,
                metadata=last_step.metadata,
                tables=last_step.tables
            )
        
        self.__steps[self.step_name] = self.__current_step

    @staticmethod
    def get_traceback(workflow: str, uuid: str) -> dict[str, StepFile] | None:
        path = os.path.join("uploads", workflow, f"{uuid}.msf")
        if not os.path.exists(path):
            return None

        with open(path, "rb") as f:
            raw = pickle.load(f)
            raw.pop("header")
            steps = raw

        return steps
    
    @staticmethod
    def pop_last_step(workflow: str, uuid: str) -> tuple[str, StepFile] | None:
        path = os.path.join("uploads", workflow, f"{uuid}.msf")
        if not os.path.exists(path):
            return None

        with open(path, "rb") as f:
            raw = pickle.load(f)
            header = raw.pop("header")
            steps = raw

        last_step_name, last_step = steps.popitem()

        with open(path, "wb") as f:
            pickle.dump({"header": header, **steps}, f)

        return last_step_name, last_step

    def complete(self, path: Optional[str] = None):
        if path is not None:
            shutil.copyfile(self.__path, path)

        if os.path.exists(self.__path):
            os.remove(self.__path)
    
    def __read(self):
        with open(self.__path, "rb") as f:
            raw = pickle.load(f)
            self.__header = raw.pop("header")
            self.__steps = raw

    def update_data(self):
        with open(self.__path, "wb") as f:
            pickle.dump({"header": self.__header, **self.__steps}, f)

    def add_table(self, label: str, table: pd.DataFrame):
        self.__current_step.tables[label] = table

    def update_table(self, label: str, table: pd.DataFrame, update_data: bool = True):
        if label not in self.__current_step.tables.keys():
            raise Exception(f"Table with label '{label}' does not exist...")
        
        self.__current_step.tables[label] = table

        if update_data:
            self.update_data()

    def remove_last_step(self) -> None:
        self.__steps.popitem()

    def get_last_step(self) -> StepFile:
        return list(self.__steps.values())[-1]
    
    def get_step(self, name: str) -> StepFile:
        return self.__steps[name]
    
    def remove_step(self, name: str) -> None:
        self.__steps.pop(name)

    @property
    def steps(self) -> list[str]:
        return list(self.__steps.keys())

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return self.__current_step.tables

    @tables.setter
    def tables(self, tables: dict[str, pd.DataFrame]):
        self.__current_step.tables = tables
    
    @property
    def metadata(self) -> dict[str, Any]:
        return self.__current_step.metadata
    
    @metadata.setter
    def metadata(self, metadata: dict[str, Any]):
        self.__current_step.metadata = metadata

    def debug(self) -> None:
        logger.debug(f"current step: {self.step_name}")
        logger.debug(f"header: {self.__header}")
        logger.debug(f"steps: {', '.join(list(self.__steps.keys()))}")
        logger.debug(f"current step: {self.__current_step.metadata}")