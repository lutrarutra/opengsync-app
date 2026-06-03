from pydantic import BaseModel


class HetznerVM(BaseModel):
    name: str