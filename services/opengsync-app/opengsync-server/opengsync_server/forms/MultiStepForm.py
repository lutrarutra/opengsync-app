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
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "args": self.args,
            "metadata": self.metadata,
            "tables": self.tables
        }
    
    def __str__(self) -> str:
        return f"StepFile(args: {self.args}, metadata: {self.metadata}, tables: {list(self.tables.keys())})"
    
    def __repr__(self) -> str:
        return self.__str__()
    

class MultiStepForm(HTMXFlaskForm):
    _step_name: str
    _workflow_name: str

    def __init__(self, workflow: str, uuid: str | None, formdata: dict | None, step_name: str, step_args: dict):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        if uuid is None:
            uuid = str(uuid4())

        if (csrf_token := self.formdata.get("csrf_token")) is None:
            self._csrf_token = self.csrf_token._value()  # type: ignore
        else:
            self._csrf_token = csrf_token

        self.step_name = step_name
        self.step_args = step_args
        self.uuid = uuid
        self.workflow = workflow

        self.__path = os.path.join("uploads", workflow, f"{uuid}.msf")
        if not os.path.exists(os.path.dirname(self.__path)):
            os.mkdir(os.path.dirname(self.__path))

        self.__header: dict[str, Any]
        self._steps: dict[str, StepFile]

        if os.path.exists(self.__path):
            self.__header, self._steps = self.__read(self.__path)
        else:
            self.__header = {
                "workflow": self.workflow,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._steps = OrderedDict()

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

        MultiStepForm.__write(uuid=uuid, path=path, header=header, steps=steps)

        return last_step_name, last_step
    
    @staticmethod
    def __read(path: str) -> tuple[dict[str, Any], dict[str, StepFile]]:
        if (cached_response := msf_cache.get(path)) is not None:
            return cached_response

        raw = pickle.load(open(path, "rb"))
        header = raw.pop("header")
        steps = raw

        return header, steps
    
    @staticmethod
    def __write(uuid: str, path: str, header: dict[str, Any], steps: dict[str, StepFile]):
        msf_cache.set(uuid, header, steps)
        with open(path, "wb") as f:
            pickle.dump({"header": header, **steps}, f)

    def fill_previous_form(self, previous_form: StepFile):
        logger.warning(f"Workflow '{self.workflow}', step '{self.step_name}', fill_previous_form() not implemented in subclass...")

    def complete(self, path: Optional[str] = None):
        if path is not None:
            shutil.copyfile(self.__path, path)

        msf_cache.delete(self.uuid)

        if os.path.exists(self.__path):
            os.remove(self.__path)

    def update_data(self):
        MultiStepForm.__write(self.uuid, self.__path, self.__header, self._steps)

    @property
    def current_step(self) -> StepFile:
        if len(self._steps) == 0:
            self._steps[self.step_name] = StepFile(
                args=self.step_args,
                metadata={},
                tables={}
            )
        elif self.step_name not in self._steps.keys():
            self._steps[self.step_name] = StepFile(
                args=self.step_args,
                metadata=self.get_last_step().metadata.copy(),
                tables=self.get_last_step().tables.copy()
            )

        return self._steps[self.step_name]
    
    def add_comment(self, context: str, text: str, update_data: bool = False):
        if (comment_table := self.tables.get("comment_table")) is None:
            comment_table = pd.DataFrame(columns=["context", "text"])
            self.add_table("comment_table", comment_table)

        comment_table.loc[len(comment_table)] = [context, text]
        self.update_table("comment_table", comment_table, update_data=update_data)

    def add_table(self, label: str, table: pd.DataFrame):
        self.current_step.tables[label] = table.copy()

    def update_table(self, label: str, table: pd.DataFrame, update_data: bool = True):
        if label not in self.current_step.tables.keys():
            raise Exception(f"Table with label '{label}' does not exist...")
        
        self.current_step.tables[label] = table.copy()

        if update_data:
            self.update_data()

    def remove_last_step(self) -> None:
        self._steps.popitem()

    def get_last_step(self) -> StepFile:
        return list(self._steps.values())[-1]
    
    def get_step(self, name: str) -> StepFile:
        return self._steps[name]
    
    def remove_step(self, name: str) -> None:
        self._steps.pop(name)

    @property
    def steps(self) -> list[str]:
        return list(self._steps.keys())

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return dict([(name, table.copy()) for name, table in self.current_step.tables.items()])

    @tables.setter
    def tables(self, tables: dict[str, pd.DataFrame]):
        self.current_step.tables = dict([(name, table.copy()) for name, table in tables.items()])
    
    @property
    def metadata(self) -> dict[str, Any]:
        return self.current_step.metadata
    
    @metadata.setter
    def metadata(self, metadata: dict[str, Any]):
        self.current_step.metadata = metadata

    def debug(self) -> None:
        logger.debug(f"""
Current step: {self.step_name}
Header: {self.__header}
Steps: {', '.join(list(self._steps.keys()))}
Metadata: {self.current_step.metadata}
""")
        
    def __str__(self) -> str:
        return f"MultiStepForm(workflow: {self.workflow}, step_name: {self.step_name}, uuid: {self.uuid})"
    
    def __repr__(self) -> str:
        return self.__str__()