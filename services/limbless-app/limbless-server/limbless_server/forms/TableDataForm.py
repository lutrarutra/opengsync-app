import os
import io
import re
import yaml
from typing import Optional, Any
from uuid import uuid4

from wtforms import StringField

import pandas as pd

from limbless_server.tools import io as io_tools


class TableDataForm():
    file_uuid = StringField()

    def __init__(self, dirname: str, uuid: Optional[str], previous_form: Optional["TableDataForm"] = None):
        self.first_step = uuid is None
        if uuid is None:
            if self.file_uuid.data is not None:
                uuid = self.file_uuid.data
            else:
                uuid = str(uuid4())

        self.uuid = uuid
        self.file_uuid.data = uuid
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
        if self.file_uuid.data is None:
            self.uuid = str(uuid4())
            self.file_uuid.data = self.uuid

        return os.path.join(self._dir, self.file_uuid.data + ".tsv")
    
    def is_loaded(self) -> bool:
        return self.__tables is not None and self.__metadata is not None
    
    def parse_file(self) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
        metadata = {}
        tables: dict[str, pd.DataFrame] = {}

        if not os.path.exists(self.path):
            if self.first_step:
                return metadata, tables
            raise FileNotFoundError(f"File '{self.path}' does not exist...")

        with open(self.path, "r") as f:
            content = f.read()
            matches = re.findall(r"\[(.*?)\]\n(.*?)(?=\n\[|$)", content, re.DOTALL)
            for label, text in matches:
                content = text.strip()
                if label == "metadata":
                    metadata = yaml.safe_load(io.StringIO(content))
                else:
                    tables[label.strip()] = pd.read_csv(
                        io.StringIO(content), delimiter="\t", index_col=None, header=0,
                        comment="#"
                    )

        self.__metadata = metadata
        self.__tables = tables
        return metadata, tables

    def update_data(self):
        buffer = io.StringIO()

        buffer.write("[metadata]\n")
        yaml.dump(self.__metadata, buffer)

        for header, content in self.__tables.items():
            buffer.write(f"[{header}]\n")
            content.to_csv(buffer, index=False, sep="\t")

        buffer.write("\n\n")

        io_tools.write_file(self.path, buffer.getvalue(), overwrite=True)

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