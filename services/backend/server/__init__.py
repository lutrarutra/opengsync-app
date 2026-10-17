import os
from importlib.metadata import version, PackageNotFoundError

# Set from the VERSION build arg in the Docker image. The backend is not installed
# as a package there (tool.uv.package = false), and a stale local server.egg-info
# would otherwise be copied into locally built images.
if (__version__ := os.environ.get("OPENGSYNC_VERSION", "")) == "":
    try:
        __version__ = version("server")
    except PackageNotFoundError:
        __version__ = "0.0.0"
