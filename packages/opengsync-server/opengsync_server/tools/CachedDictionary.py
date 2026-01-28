from typing import Any, Hashable

from .RedisMSFFileCache import RedisMSFFileCache

class CachedDictionary:
    def __init__(self, template: str, msf_cache: RedisMSFFileCache, steps: list[str]):
        self.__data: dict | None = None
        self.template = template
        self.r = msf_cache
        self.steps = steps
        self.steps.reverse()
        self.current_step = steps[0]

    def key(self, step_name: str) -> str:
        return self.template.format(step=step_name)

    @property
    def data(self) -> dict:
        if self.__data is None:
            for step in self.steps:
                if (data := self.r.get_dict(self.key(step))) is not None:
                    self.__data = data
                    break
            else:
                self.__data = {}

        return self.__data
    
    @data.setter
    def data(self, value: dict) -> None:
        self.__data = value
        self.r.set_dict(self.key(self.current_step), self.__data)

    def __getitem__(self, key: str) -> Any:
        return self.data[key]
    
    def __setitem__(self, key: Hashable, value: Any) -> None:        
        self.data[key] = value
        self.r.set_dict(self.key(self.current_step), self.data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
    
    def pop(self, key: str, default: Any = None) -> Any:
        value = self.data.pop(key, default)
        self.r.set_dict(self.key(self.current_step), self.data)
        return value
    
    def clear(self) -> None:
        self.__data = {}
        self.r.set_dict(self.key(self.current_step), self.__data)

    def items(self):
        return self.data.items()
    
    def keys(self):
        return self.data.keys()
    
    def values(self):
        return self.data.values()
    
    def __contains__(self, key: str) -> bool:
        return key in self.data
    
    def __repr__(self) -> str:
        return repr(self.data)
    
    def __len__(self) -> int:
        return len(self.data)
