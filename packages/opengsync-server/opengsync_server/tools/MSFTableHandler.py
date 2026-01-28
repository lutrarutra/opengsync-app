import pandas as pd

from .RedisMSFFileCache import RedisMSFFileCache

class MSFTableHandler:
    def __init__(self, template: str, msf_cache: RedisMSFFileCache, steps: list[str]):
        self.__tables: dict[str, pd.DataFrame] = {}
        self.template = template
        self.r = msf_cache
        self.steps = steps
        self.steps.reverse()
        self.current_step = steps[0]

    def key(self, step_name: str, table_name: str) -> str:
        return self.template.format(step=step_name, table=table_name)

    def __getitem__(self, key: str) -> pd.DataFrame:
        if key in self.__tables:
            return self.__tables[key]
        
        for step in self.steps:
            if (table := self.r.get_table(self.key(step, key))) is not None:
                self.__tables[key] = table
                return table

        raise KeyError(f"Table '{key}' not found in StepTables.")
    
    def __setitem__(self, key: str, table: pd.DataFrame) -> None:
        self.__tables[key] = table
        self.r.set_table(self.key(self.current_step, key), table)

    def get(self, key: str) -> pd.DataFrame | None:
        try:
            return self[key]
        except KeyError:
            return None
        
    def keys(self) -> list[str]:
        tables = list(self.__tables.keys())
        if self.r is None:
            raise RuntimeError("You need to call connect() before using the cache.")
        
        for step in self.steps:
            for key in self.r.r.scan_iter(match=self.key(step, "*")):  # type: ignore
                table_name = key.decode('utf-8').split(":")[-1]
                if table_name not in tables:
                    tables.append(table_name)
        return tables