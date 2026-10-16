"""Reading the cells of a rendered spreadsheet: QueryColumn ids by their names, DBObjectColumn "name [id]" options."""

import json
import re
from typing import Any


def query_labels(response, title: str) -> dict[int, str]:
    """Names of the ids of the QueryColumn titled ``title``, as sent to its editor."""
    match = re.search(
        r'\{ type: jssQueryColumn, title: ' + re.escape(json.dumps(title)) + r', [^\n]*?labels: (\{[^\n]*?\})(?:, \w+: [^\n]*?)? \}',
        response.text,
    )
    assert match is not None, f"no query column '{title}' in response"
    return {int(object_id): name for object_id, name in json.loads(match.group(1)).items()}


def object_name(value: Any) -> Any:
    """The name of a "name [id]" / "name [new]" option."""
    if isinstance(value, str) and value.endswith("]") and " [" in value:
        return value.rpartition(" [")[0]
    return value


def object_id(value: Any) -> int | None:
    """The id of a "name [id]" option, None for "name [new]" and empty cells."""
    if isinstance(value, str) and (match := re.search(r" \[(\d+)\]$", value)):
        return int(match.group(1))
    return None
