"""Share visibility rules shared by the live share browser and the fs-index.

`.ngsignore` files are gitignore-style: one in directory D applies to D and everything below it, with
patterns relative to D; the nearest file with a matching rule decides, and nothing below an ignored
directory can be re-included. The ignore files themselves are always hidden.
"""
import re
from collections.abc import Callable, Mapping

import pathspec

IGNORE_FILENAME = ".ngsignore"

OS_JUNK_REGEX = re.compile(
    r'(^|/)'
    r'('
    r'\._'                        # AppleDouble
    r'|\.DS_Store'                # macOS folder config
    r'|Thumbs\.db|desktop\.ini'   # Windows junk
    r'|\.Spotlight-V100|\.Trashes|\.metadata_|\.com\.apple\.timemachine'  # macOS indexing/system
    r'|\.hidden'                  # Linux hidden file list
    r'|\.ignored'                 # Common user-level ignore file
    r'|^Network Trash Folder$'    # Old macOS network junk
    r'|^Temporary Items$'         # macOS temp folder
    r')',
    re.IGNORECASE
)

# (directory path relative to the spec's directory, spec), nearest spec first
Specs = tuple[tuple[str, pathspec.GitIgnoreSpec], ...]


def is_junk(path: str) -> bool:
    """`path` is POSIX; a junk component anywhere in it makes everything below junk too."""
    return bool(OS_JUNK_REGEX.search(path.rsplit("/", 1)[-1]) or OS_JUNK_REGEX.search(path))


def parse_ignore_text(text: str, on_invalid: Callable[[str], None] | None = None) -> pathspec.GitIgnoreSpec:
    """Invalid lines are skipped (and reported to `on_invalid`) instead of invalidating the whole file."""
    lines = []
    for line in text.splitlines():
        try:
            pathspec.GitIgnoreSpec.from_lines([line])
        except ValueError:
            if on_invalid is not None:
                on_invalid(line)
            continue
        lines.append(line)
    return pathspec.GitIgnoreSpec.from_lines(lines)


def decide(specs: Specs, name: str) -> bool:
    """`name` ends with "/" for a directory."""
    for prefix, spec in specs:
        if (include := spec.check_file(prefix + name).include) is not None:
            return include
    return False


class IgnoreRules:
    """Evaluates `.ngsignore` rules for share-root relative POSIX paths from in-memory file contents.

    `files` maps a directory path ("" for the share root) to its ignore file's text, or None when the file
    exists but could not be read, which hides that directory's contents.
    """

    def __init__(self, files: Mapping[str, str | None]):
        self._specs: dict[str, pathspec.GitIgnoreSpec] = {
            directory: parse_ignore_text(text) for directory, text in files.items() if text is not None
        }
        self._unreadable = {directory for directory, text in files.items() if text is None}
        self._dirs: dict[str, tuple[bool, Specs]] = {}

    @property
    def empty(self) -> bool:
        return not self._specs and not self._unreadable

    def is_hidden(self, path: str, is_dir: bool, link_target: str | None = None) -> bool:
        """Hidden by its own path or, for a symlink, by the path it points to."""
        if self._matches(path, is_dir):
            return True
        return link_target is not None and link_target != path and self._matches(link_target, is_dir)

    def hides_below(self, directory: str) -> bool:
        return self._dir_state(directory)[0]

    def _matches(self, path: str, is_dir: bool) -> bool:
        parent, _, name = path.rpartition("/")
        if name == IGNORE_FILENAME:
            return True
        if self.empty:
            return False
        hidden_below, specs = self._dir_state(parent)
        if hidden_below:
            return True
        return bool(specs) and decide(specs, name + "/" if is_dir else name)

    def _dir_state(self, directory: str) -> tuple[bool, Specs]:
        """(everything below `directory` is hidden, the specs that apply to its entries)"""
        if (state := self._dirs.get(directory)) is not None:
            return state
        if directory == "":
            hidden_below, specs = False, ()
        else:
            parent, _, name = directory.rpartition("/")
            parent_hidden, parent_specs = self._dir_state(parent)
            # an ignored directory hides everything below it, so nothing there can be re-included
            hidden_below = parent_hidden or decide(parent_specs, name + "/")
            specs = tuple((f"{prefix}{name}/", spec) for prefix, spec in parent_specs)
        if (spec := self._specs.get(directory)) is not None:
            specs = (("", spec), *specs)
        state = self._dirs[directory] = (hidden_below or directory in self._unreadable, specs)
        return state
