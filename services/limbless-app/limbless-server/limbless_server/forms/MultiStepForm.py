import os
import datetime
from typing import Optional, Any, OrderedDict
from uuid import uuid4
from dataclasses import dataclass

import pickle
import pandas as pd

from .. import msf_cache, logger
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
            self.__header, self.__steps = self.__read(self.__path)
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

        _, steps = MultiStepForm.__read(path)

        return steps
    
    @staticmethod
    def pop_last_step(workflow: str, uuid: str) -> tuple[str, StepFile] | None:
        path = os.path.join("uploads", workflow, f"{uuid}.msf")
        if not os.path.exists(path):
            return None

        header, steps = MultiStepForm.__read(path)
        last_step_name, last_step = steps.popitem()
        MultiStepForm.__write(uuid, path, header, steps)

        return last_step_name, last_step
    
    @staticmethod
    def __read(path: str) -> tuple[dict[str, Any], dict[str, StepFile]]:
        if (cached_response := msf_cache.get(path)) is not None:
            return cached_response
        
        with open(path, "rb") as f:
            raw = pickle.load(f)
            header = raw.pop("header")
            steps = raw

        return header, steps
    
    @staticmethod
    def __write(uuid: str, path: str, header: dict[str, Any], steps: dict[str, StepFile]):
        msf_cache.set(uuid, header, steps)
        with open(path, "wb") as f:
            pickle.dump({"header": header, **steps}, f)

    def fill_previous_form(self):
        logger.warning(f"Workflow '{self.workflow}', step '{self.step_name}', fill_previous_form() not implemented in subclass...")

    def complete(self, path: Optional[str] = None):
        if path is not None:
            shutil.copyfile(self.__path, path)

        msf_cache.delete(self.uuid)

        if os.path.exists(self.__path):
            os.remove(self.__path)

    def update_data(self):
        MultiStepForm.__write(self.uuid, self.__path, self.__header, self.__steps)

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