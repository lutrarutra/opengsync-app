from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

from ...components import inputs
from ...components.inputs.dynamic import SubFormList
from ...core import config, exceptions as exc
from ...utils import parsing
from ...utils.file_browser import is_within_root, MAX_SELECTED_PATHS
from ..SubHTMXForm import SubHTMXForm


class SelectedPathSubForm(SubHTMXForm):
    path = inputs.string.StringInputField("Path", required=True, hidden=True)


class _SelectedPathsForm(Protocol):
    paths: SubFormList[SelectedPathSubForm]
    _context: dict[str, Any]

    def add_general_error(self, error: str) -> None:
        ...


class SelectedPathsMixin:
    """Share-root paths picked in the insider file browser, as a `paths` SubFormList of SelectedPathSubForm.

    The template renders them with components/selected-paths.jinja2.
    """

    @staticmethod
    def collapse_paths(paths: Iterable[str]) -> list[str]:
        """Without duplicates or paths inside another listed path, which that path already covers."""
        return sorted(parsing.filter_subpaths(list(dict.fromkeys(path for path in paths if path))))

    def prefill_paths(self: _SelectedPathsForm, paths: Iterable[str]) -> None:
        """One entry per collapsed path; the template says how many were left out as covered by a listed folder."""
        unique = list(dict.fromkeys(path for path in paths if path))
        collapsed = SelectedPathsMixin.collapse_paths(unique)
        for path in collapsed:
            self.paths.append_entry().path.data = path
        self._context["covered_paths"] = len(unique) - len(collapsed)

    def assert_path_count(self: _SelectedPathsForm) -> None:
        if len(self.paths) > MAX_SELECTED_PATHS:
            self.add_general_error(f"At most {MAX_SELECTED_PATHS} paths can be selected at once.")
            raise exc.FormValidationException(self)

    @staticmethod
    def exists(path: str | None) -> bool:
        """Whether the path is on the share now, so the form can warn about e.g. stale search results."""
        if not path:
            return False
        share_root = Path(config.settings.app_config.share_root)
        return is_within_root(share_root, path) and (share_root / path).exists()

    @staticmethod
    def is_directory(path: str | None) -> bool:
        """For the list's folder/file icon. Only looks inside the share root."""
        if not path:
            return False
        share_root = Path(config.settings.app_config.share_root)
        return is_within_root(share_root, path) and (share_root / path).is_dir()
