from .OpeNGSyncAPI import OpeNGSyncAPI

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("opengsync-api")
except PackageNotFoundError:
    __version__ = "0.0.0"