from typing import Any

import pint
from pint import UnitRegistry

registry = UnitRegistry()


registry.define("bp = [length] = basepair")
registry.define("Kbp = 1e3 * bp = kilobasepair")
registry.define("Mbp = 1e6 * bp = megabasepair")
registry.define("Gbp = 1e9 * bp = gigabasepair")

registry.define("Kcount = 1e3 * count = kilocount")
registry.define("Mcount = 1e6 * count = megacount")
registry.define("Gcount = 1e9 * count = gigacount")

registry.define("read = []")
registry.define("Kread = 1e3 * read = kiloread")
registry.define("Mread = 1e6 * read = megaread")
registry.define("Bread = 1e9 * read = gigaread")

registry.define("Million = 1e6 = million")
registry.define("Billion = 1e9 = billion")


def from_dict(d: dict[str, Any]) -> pint.Quantity:
    return d["value"] * registry(d["unit"])


def to_dict(q: pint.Quantity) -> dict[str, Any]:
    return {
        "value": q.magnitude,
        "unit": str(q.units)
    }


def make(value: float, unit: str) -> pint.Quantity:
    return value * registry(unit)


    
    