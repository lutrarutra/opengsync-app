"""Disposable SQLite index of the share roots for search and folder sizes.

The worker is its only writer (import of cluster dumps, mtime-driven crawler); the app only reads it.
"""
from .models import FsIndexBase, Entry, IgnoreFile, Meta
from .ignore import IGNORE_FILENAME, OS_JUNK_REGEX, IgnoreRules, decide, is_junk, parse_ignore_text
from .schema import (
    SCHEMA_VERSION, ancestor_paths, create_fts_triggers, drop_fts_triggers, ensure_schema,
    parent_path, rebuild_fts, subtree_bounds,
)
from .handler import FsIndexDBHandler, FsIndexUnavailable, connect_writer

__all__ = [
    "FsIndexBase", "Entry", "IgnoreFile", "Meta",
    "IGNORE_FILENAME", "OS_JUNK_REGEX", "IgnoreRules", "decide", "is_junk", "parse_ignore_text",
    "SCHEMA_VERSION", "ancestor_paths", "create_fts_triggers", "drop_fts_triggers",
    "ensure_schema", "parent_path", "rebuild_fts", "subtree_bounds",
    "FsIndexDBHandler", "FsIndexUnavailable", "connect_writer",
]
