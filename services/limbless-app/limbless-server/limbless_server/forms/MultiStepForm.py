import os
from typing import Optional, Any
from uuid import uuid4

import pandas as pd

from limbless_server.tools import io as iot

from .. import config_cache, logger
from .HTMXFlaskForm import HTMXFlaskForm


class MultiStepForm(HTMXFlaskForm):
    def __init__(self, dirname: str, uuid: str | None, formdata: dict, previous_form: Optional["MultiStepForm"] = None):
        HTMXFlaskForm.__init__(self, formdata=formdata)
        self.first_step = uuid is None
        if uuid is None:
            uuid = str(uuid4())

        self.uuid = uuid
        self._dir = os.path.join("uploads", dirname)

        self.__metadata: dict[str, Any]
        self.__tables: dict[str, pd.DataFrame]

        if previous_form is not None:
            self.__metadata = previous_form.metadata
            self.__tables = previous_form.tables
        else:
            self.__metadata, self.__tables = self.parse_file()
        
        if not os.path.exists(self._dir):
            os.mkdir(self._dir)

    @property
    def path(self) -> str:
        return os.path.join(self._dir, self.uuid + f"{self.step_num}.msf")
    
    def is_loaded(self) -> bool:
        return self.__tables is not None and self.__metadata is not None
    
    def parse_file(self) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
        if (response := config_cache.get(self.uuid)) is not None:
            logger.debug(f"Using cached data for form '{self.uuid}'")
            self.__metadata = response[0]
            self.__tables = response[1]
            return response[0], response[1]
        
        if not os.path.exists(self.path):
            if not os.path.exists(self.path):
                if self.first_step:
                    return {}, {}
                raise FileNotFoundError(f"File '{self.path}' does not exist...")
        
        self.__metadata, self.__tables = iot.parse_config_tables(self.path)
        return self.__metadata, self.__tables

    def update_data(self):
        config_cache.set(self.uuid, self.__metadata, self.__tables)
        iot.write_config_file(self.path, self.__metadata, self.__tables)

    def add_table(self, label: str, table: pd.DataFrame):
        self.__tables[label] = table

    def update_table(self, label: str, table: pd.DataFrame, update_data: bool = True):
        if label not in self.__tables.keys():
            raise Exception(f"Table with label '{label}' does not exist...")
        
        self.__tables[label] = table

        if update_data:
            self.update_data()

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        return self.__tables

    @tables.setter
    def tables(self, tables: dict[str, pd.DataFrame]):
        self.__tables = tables
    
    @property
    def metadata(self) -> dict[str, Any]:
        return self.__metadata
    
    @metadata.setter
    def metadata(self, metadata: dict[str, Any]):
        self.__metadata = metadata