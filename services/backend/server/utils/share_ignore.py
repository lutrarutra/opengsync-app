"""Gitignore-style `.ngsignore` files that hide paths from share links.

A `.ngsignore` in directory D applies to D and everything below it, with patterns
relative to D. Every ignore file from the share root down to a path applies, and the
nearest one with a matching rule decides. Once a directory is ignored nothing below it
can be re-included. The ignore files themselves are always hidden.

Only `SharedFileBrowser` (share-link access) applies these rules; the insider
`FileBrowser` shows everything. Share listings, PROPFIND responses and walks are
cached in Redis in prod, so an edited `.ngsignore` reaches those after their TTL.
"""

import os

import pathspec
from loguru import logger

IGNORE_FILENAME = ".ngsignore"

# (directory path relative to the spec's directory, spec), nearest spec first
Specs = tuple[tuple[str, pathspec.GitIgnoreSpec], ...]


class ShareIgnore:
    """Evaluates each directory once and works on plain strings: this runs for every entry of listings and walks."""

    def __init__(self, root_dir: str | os.PathLike[str]):
        self.root = os.path.realpath(root_dir)
        self._root_prefix = self.root if self.root.endswith(os.sep) else self.root + os.sep
        self._dirs: dict[str, tuple[bool, Specs]] = {}
        self._real_dirs: dict[str, str] = {}

    def is_ignored(self, path: str | os.PathLike[str], is_dir: bool | None = None) -> bool:
        """True if a `.ngsignore` hides `path`, either by its own path or by the path its symlinks resolve to.

        Pass `is_dir` when it is already known to save a stat.
        """
        path = os.path.normpath(path)
        if not self._is_inside(path):
            return False
        if self._matches(path, is_dir):
            return True
        try:
            if os.path.islink(path):
                real_path = os.path.realpath(path)
            else:
                parent, name = os.path.split(path)
                real_path = os.path.join(self._real_dir(parent), name)
        except (OSError, RuntimeError):
            return True
        return real_path != path and self._is_inside(real_path) and self._matches(real_path, is_dir)

    def _is_inside(self, path: str) -> bool:
        """Strictly below the root; the root itself is never ignored."""
        return path.startswith(self._root_prefix) and path != self.root

    def _real_dir(self, directory: str) -> str:
        if (real := self._real_dirs.get(directory)) is None:
            real = self._real_dirs[directory] = os.path.realpath(directory)
        return real

    def _matches(self, path: str, is_dir: bool | None) -> bool:
        parent, name = os.path.split(path)
        if name == IGNORE_FILENAME:
            return True
        hidden_below, specs = self._dir_state(parent)
        if hidden_below:
            return True
        if not specs:
            return False
        if is_dir is None:
            is_dir = os.path.isdir(path)
        return self._decide(specs, name + "/" if is_dir else name)

    @staticmethod
    def _decide(specs: Specs, name: str) -> bool:
        for prefix, spec in specs:
            if (include := spec.check_file(prefix + name).include) is not None:
                return include
        return False

    def _dir_state(self, directory: str) -> tuple[bool, Specs]:
        """(everything below `directory` is hidden, the specs that apply to its entries)"""
        if (state := self._dirs.get(directory)) is not None:
            return state
        if directory == self.root:
            hidden_below, specs = False, ()
        else:
            parent, name = os.path.split(directory)
            parent_hidden, parent_specs = self._dir_state(parent)
            # an ignored directory hides everything below it, so nothing there can be re-included
            hidden_below = parent_hidden or self._decide(parent_specs, name + "/")
            specs = tuple((f"{prefix}{name}/", spec) for prefix, spec in parent_specs)
        spec, unreadable = self._load(directory)
        if spec is not None:
            specs = (("", spec), *specs)
        state = self._dirs[directory] = (hidden_below or unreadable, specs)
        return state

    def _load(self, directory: str) -> tuple[pathspec.GitIgnoreSpec | None, bool]:
        """(parsed ignore file of `directory`, whether it exists but could not be read)"""
        ignore_file = os.path.join(directory, IGNORE_FILENAME)
        try:
            with open(ignore_file, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
            return None, False
        except OSError:
            logger.warning(f"Could not read {ignore_file}, hiding {directory} from share links")
            return None, True

        lines = []
        for line in text.splitlines():
            try:
                pathspec.GitIgnoreSpec.from_lines([line])
            except ValueError:
                logger.warning(f"Skipping invalid pattern {line!r} in {ignore_file}")
                continue
            lines.append(line)
        return pathspec.GitIgnoreSpec.from_lines(lines), False
