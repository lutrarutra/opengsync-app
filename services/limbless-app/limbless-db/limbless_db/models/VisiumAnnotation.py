from sqlmodel import Field, SQLModel


class VisiumAnnotation(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    slide: str = Field(nullable=False, max_length=64)
    area: str = Field(nullable=False, max_length=8)
    image: str = Field(nullable=False, max_length=128)