import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class FsIndexBase(DeclarativeBase):
    """Separate from `opengsync_db.models.Base`: the fs-index lives in its own SQLite file, outside Alembic."""


class Entry(FsIndexBase):
    """One file, directory or symlink under the share root.

    `path` is share-root relative and starts with the root's name (`BSF_PROJECTS/a/b`), like `DataPath.path`.
    Directory totals cover their visible descendants (not `hidden`, not `unsafe`), including the contents of
    `opaque` directories, whose children are not stored.
    """
    __tablename__ = "entry"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    path: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    parent_id: Mapped[int | None] = mapped_column(sa.Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # d: directory, f: file, l: symlink, o: other
    kind: Mapped[str] = mapped_column(sa.String(1), nullable=False)
    size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # NULL for a directory that was never listed, so the crawler lists it
    mtime: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    # symlinks: share-root relative target, NULL when it points outside the share roots
    link_target: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    target_kind: Mapped[str | None] = mapped_column(sa.String(8), nullable=True)
    target_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    # hidden from share links by a .ngsignore
    hidden: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # a symlink leaving the share roots, which share links refuse
    unsafe: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    # excluded from search (config `index_ignore`), still counted in totals
    searchable: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    # directory whose children are not stored (index_ignore match); its totals come from the dump
    opaque: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    # directories only
    total_size: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    n_files: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    max_mtime: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    next_check_at: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    check_interval: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

    __table_args__ = (
        sa.Index("ix_entry_due", "next_check_at", sqlite_where=sa.text("kind = 'd' AND next_check_at IS NOT NULL")),
    )


class IgnoreFile(FsIndexBase):
    """Contents of each `.ngsignore`, so hidden flags are computed without reading the mount. NULL: unreadable."""
    __tablename__ = "ignore_file"

    dir_path: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    content: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class Meta(FsIndexBase):
    __tablename__ = "meta"

    key: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    value: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
