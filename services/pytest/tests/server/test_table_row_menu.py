"""Table rows keep their actions in the ⋯ menu; right-click menus in tables only copy (docs/tables.md).

Right-click is invisible and absent on touch screens, so a "Remove Library" there is hard to find and easy
to hit by accident. Every row template (templates/components/tables/rows/) may only put ``copy`` actions in a
``context_menu([...])``; anything that changes data (hxdelete, hxpost, hxget, mailto, select) belongs in the
row's ``row_menu([...])``, whose variant then needs ``actions=True`` so the header has a cell for it.
"""
import re
from pathlib import Path

from fastapi.testclient import TestClient

ACTION_TYPE = re.compile(r"""["']type["']\s*:\s*["'](\w+)["']""")


def _rows_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [Path("/templates")] + [parent / "services/backend/templates" for parent in here.parents]
    for candidate in candidates:
        if (candidate / "components/tables/rows").is_dir():
            return candidate / "components/tables/rows"
    raise AssertionError("row templates not found")


def _calls(source: str, name: str) -> list[str]:
    """The argument lists of every ``name([...])`` call."""
    calls, pos = [], 0
    while (start := source.find(f"{name}([", pos)) != -1:
        i = start + len(name) + 2
        depth = 1
        while depth and i < len(source):
            depth += {"[": 1, "]": -1}.get(source[i], 0)
            i += 1
        calls.append(source[start + len(name) + 2:i - 1])
        pos = i
    return calls


def test_right_click_menus_in_tables_only_copy():
    problems = []
    for path in sorted(_rows_dir().glob("*.html")):
        source = path.read_text()
        for call in _calls(source, "context_menu"):
            if bad := sorted({t for t in ACTION_TYPE.findall(call) if t not in ("copy", "copy_column")}):
                problems.append(f"{path.name}: right-click menu with {bad}, move them to row_menu")
    assert not problems, "\n".join(problems)


def test_row_menus_have_an_actions_column(client: TestClient):
    from server.components.tables import Table

    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    templates = _rows_dir().parents[2]

    def source(path: Path) -> str:
        """The template with the templates it includes (one level)."""
        text = path.read_text()
        for include in re.findall(r'{%\s*include\s+"([^"]+)"', text):
            if (templates / include).is_file():
                text += (templates / include).read_text()
        return text

    with_menu = {p.name for p in _rows_dir().glob("*.html") if "row_menu(" in source(p)}
    problems = []
    for table in subclasses(Table):
        for name, variant in table.variants.items():
            template = Path(variant.row_template).name
            if (template in with_menu) != variant.actions:
                problems.append(
                    f"{table.__name__}.variants['{name}']: actions={variant.actions} but {template} "
                    f"{'has' if template in with_menu else 'has no'} row_menu"
                )
    assert not problems, "\n".join(problems)
