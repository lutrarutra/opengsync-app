import os
from typing import Optional, Any
from uuid import uuid4

from wtforms import StringField

import pandas as pd

from ..tools import io as iot


class TableDataForm():
    file_uuid = StringField()

    def __init__(self, uuid: Optional[str]):
        if uuid is None:
            if self.file_uuid.data is not None:
                uuid = self.file_uuid.data
            else:
                uuid = str(uuid4())

        self.uuid = uuid
        self.file_uuid.data = uuid

        self.__data = None

    @property
    def path(self) -> str:
        if self.file_uuid.data is None:
            self.uuid = str(uuid4())
            self.file_uuid.data = self.uuid

        return os.path.join("uploads", "seq_request", self.file_uuid.data + ".tsv")

    def get_data(self) -> dict[str, pd.DataFrame]:
        if self.__data is None:
            self.__data = iot.parse_config_tables(self.path, sep="\t")

        return self.__data
    
    def update_data(self, data: dict[str, pd.DataFrame]):
        self.__data = data
        iot.write_config_tables_from_sections(self.path, data, sep="\t", overwrite=True)