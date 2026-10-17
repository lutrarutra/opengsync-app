from pathlib import Path

import pytest

from opengsync_db.transitions import docs


def _find_doc() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "docs" / "state-transitions.md"
        if candidate.exists():
            return candidate
    pytest.fail("docs/state-transitions.md not found (is ./docs mounted in compose.test.yaml?)")


def test_generated_section_is_up_to_date():
    document = _find_doc().read_text()
    assert docs.extract_generated(document) == docs.render(), (
        "docs/state-transitions.md is out of date; run: python -m opengsync_db.transitions.docs --write"
    )


def test_replace_generated_roundtrip():
    document = f"intro\n\n{docs.BEGIN}\nold\n{docs.END}\n\noutro\n"
    replaced = docs.replace_generated(document, docs.render())
    assert replaced.startswith("intro\n\n" + docs.BEGIN)
    assert replaced.endswith(docs.END + "\n\noutro\n")
    assert docs.extract_generated(replaced) == docs.render()
