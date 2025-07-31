from dataclasses import dataclass, field
from typing import ClassVar

Number = int | float


@dataclass(frozen=True)
class Dimension:
    name: str
    symbol: str | None

    _order: list["Unit"] = field(default_factory=list)

    _units: ClassVar[dict[str, "Unit"]] = dict()
    _registry: ClassVar[dict[str, "Dimension"]] = dict()

    def __post_init__(self):
        Dimension._registry[self.name] = self

    @property
    def units(self) -> list["Unit"]:
        return self._order
    
    @classmethod
    def __class_getitem__(cls, name: str) -> "Unit":
        return cls._units[name]


@dataclass(frozen=True)
class Unit:
    dimension: Dimension
    name: str
    factor_to_base: float
    base_unit: "Unit"
    symbol: str | None
    multiplier_suffix: str | None

    def __init__(self, dim: Dimension, name: str, factor: float, symbol: str | None = None, base: "Unit | None" = None, suffix: str | None = None):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "dimension", dim)
        object.__setattr__(self, "symbol", symbol if symbol is not None else dim.symbol)
        object.__setattr__(self, "factor_to_base", factor)
        object.__setattr__(self, "base_unit", base if base is not None else self)
        object.__setattr__(self, "multiplier_suffix", suffix)
        dim._units[name] = self
        dim._order.append(self)
        dim._order.sort(key=lambda u: u.factor_to_base)

    @classmethod
    def all(cls, dimension: Dimension) -> list["Unit"]:
        return dimension._order

    def __rmul__(self, value: Number) -> "Quantity":
        return Quantity(float(value), self)
    
    def ensure_same_dimension(self, other: "Unit") -> None:
        if self.dimension != other.dimension:
            raise ValueError(f"Dimension mismatch: {self.dimension.name} vs {other.dimension.name}")
        
    def next(self) -> "Unit | None":
        units = Unit.all(self.dimension)
        idx = 0
        for idx, unit in enumerate(units):
            if unit.factor_to_base == self.factor_to_base:
                break
        return units[idx + 1] if idx + 1 < len(units) else None
    
    def prev(self) -> "Unit | None":
        units = Unit.all(self.dimension)
        idx = 0
        for idx, unit in enumerate(units):
            if unit.factor_to_base == self.factor_to_base:
                break
        return units[idx - 1] if idx - 1 >= 0 else None

    def __repr__(self) -> str:
        return f"Unit(dimension={self.dimension.name}, unit={self.name}, base_unit={self.base_unit.symbol}, factor={self.factor_to_base}, suffix={self.multiplier_suffix})"
    

@dataclass(frozen=True)
class Quantity:
    value: float | int
    unit: Unit
    prev_unit: Unit | None = None
    next_unit: Unit | None = None

    def to(self, other: Unit) -> "Quantity":
        self.unit.ensure_same_dimension(other)
        v_other = self.value * (self.unit.factor_to_base / other.factor_to_base)
        return Quantity(v_other, other)
    
    def to_base(self) -> "Quantity":
        if self.unit.base_unit is None:
            return self
        return Quantity(self.value * self.unit.factor_to_base, self.unit.base_unit)

    def __add__(self, other: "Quantity") -> "Quantity":
        self.unit.ensure_same_dimension(other.unit)
        other_in_self = other.to(self.unit)
        return Quantity(self.value + other_in_self.value, self.unit)

    def __sub__(self, other: "Quantity") -> "Quantity":
        self.unit.ensure_same_dimension(other.unit)
        other_in_self = other.to(self.unit)
        return Quantity(self.value - other_in_self.value, self.unit)

    def __mul__(self, k: Number) -> "Quantity":
        return Quantity(self.value * float(k), self.unit)

    def __truediv__(self, k: Number) -> "Quantity":
        return Quantity(self.value / float(k), self.unit)

    def __repr__(self) -> str:
        return f"Quantity(value={self.value * self.unit.factor_to_base:g}, unit={self.unit.symbol})"
    
    def value_to_str(self, n_digits: int = 3) -> str:
        if self.unit.multiplier_suffix:
            return f"{float(f'{self.value:.{n_digits}g}')} {self.unit.multiplier_suffix}"
        return f"{round(self.value, n_digits):.{n_digits}f}"
    
    @property
    def base(self) -> "Quantity":
        return self.to_base()

    @property
    def base_value(self) -> float:
        return self.value * self.unit.factor_to_base
    
    @property
    def base_unit(self) -> Unit:
        return self.to_base().unit
    
    def compact(self, threshold: int = 3) -> "Quantity":
        if self.value > 10**threshold:
            if (n := self.unit.next()) is not None:
                return self.to(n).compact()
            
        elif self.value < 1.0 / (10 ** threshold):
            if (p := self.unit.prev()) is not None:
                return self.to(p).compact()
        return self
    
    @property
    def is_base_unit(self) -> bool:
        return self.unit.name == self.unit.base_unit.name
    
    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "value": self.base_value,
            "unit": self.base_unit.name,
            "dimension": self.unit.dimension.name,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Quantity":
        return data["value"] * Dimension._registry[data["dimension"]]._units[data["unit"]]
    

def from_dict(data: dict) -> Quantity:
    """Create a Quantity from a dictionary."""
    if "value" not in data or "unit" not in data or "dimension" not in data:
        raise ValueError("Invalid data for Quantity")
    
    return Quantity.from_dict(data)


def to_dict(quantity: Quantity) -> dict[str, float | int | str | None]:
    """Convert a Quantity to a dictionary."""
    return quantity.to_dict()
    

read_count = Dimension("read_count", "reads")

read = Unit(
    name="read",
    dim=read_count,
    factor=1.0,
)

k_read = Unit(
    name="k_read",
    dim=read_count,
    factor=1e3,
    suffix="K",
    base=read
)
m_read = Unit(
    name="m_read",
    dim=read_count,
    factor=1e6,
    suffix="M",
    base=read
)
g_read = Unit(
    name="g_read",
    dim=read_count,
    factor=1e9,
    suffix="B",
    base=read
)
b_read = Unit(
    name="b_read",
    dim=read_count,
    factor=1e9,
    suffix="B",
    base=read
)

percentage = Dimension("percentage", "%")
percent = Unit(
    name="percent",
    dim=percentage,
    factor=1.0,
)
permille = Unit(
    name="permille",
    dim=percentage,
    factor=1e-3,
    symbol="‰",
    base=percent
)

count_dim = Dimension("count", None)

count = Unit(
    name="count",
    dim=count_dim,
    factor=1.0,
)

mu_count = Unit(
    name="micro_count",
    dim=count_dim,
    factor=1e-6,
    suffix="μ",
    base=count
)

k_count = Unit(
    name="k_count",
    dim=count_dim,
    factor=1e3,
    suffix="K",
    base=count
)

m_count = Unit(
    name="m_count",
    dim=count_dim,
    factor=1e6,
    suffix="M",
    base=count
)

b_count = Unit(
    name="b_count",
    dim=count_dim,
    factor=1e9,
    suffix="B",
    base=count
)