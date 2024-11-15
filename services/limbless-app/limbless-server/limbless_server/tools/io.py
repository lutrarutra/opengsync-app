import io
import os
import re
import yaml
import hashlib
from typing import Optional, Any

import pandas as pd

from .. import logger


def calculate_md5_from_file(path: str) -> str:
    md5_hash = hashlib.md5()
    with open(path, "rb") as f:
        # Read the file in chunks and update the hash
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)
    return md5_hash.hexdigest()


def calculate_md5_from_string(data: str) -> str:
    md5_hash = hashlib.md5()
    md5_hash.update(data.encode("utf-8"))
    return md5_hash.hexdigest()


def write_file(path: str, content: str, overwrite: bool = False, chunk_size: int = 1024) -> bool:
    if os.path.exists(path):
        if calculate_md5_from_file(path) == calculate_md5_from_string(content):
            logger.debug(f"Skipping, no changes in file: {path}")
            return False

        if overwrite:
            logger.debug(f"Overwriting existing file: {path}")
        else:
            logger.debug(f"Skipping, file already exists: {path}")
            return False
    else:
        logger.debug(f"Writing file to: {path}")

    with open(path, "w") as file:
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            file.write(chunk)

    return True


def mkdir(path: str) -> str:
    if not os.path.exists(path):
        os.makedirs(path)

    return path


def parse_config_tables(path: str) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    metadata = {}
    tables: dict[str, pd.DataFrame] = {}

    with open(path, "r") as f:
        content = f.read()
        matches = re.findall(r"\[(.*?)\]\n(.*?)(?=\n\[|$)", content, re.DOTALL)
        for label, text in matches:
            content = text.strip()
            if label == "metadata":
                metadata = yaml.safe_load(io.StringIO(content))
            else:
                tables[label.strip()] = pd.read_csv(
                    io.StringIO(content), delimiter="\t", index_col=None, header=0,
                )

    return metadata, tables


def write_config_file(path: str, metadata: dict[str, Any], tables: dict[str, pd.DataFrame]):
    buffer = io.StringIO()

    buffer.write("[metadata]\n")
    yaml.dump(metadata, buffer)

    for header, content in tables.items():
        buffer.write(f"[{header}]\n")
        content.to_csv(buffer, index=False, sep="\t")

    buffer.write("\n\n")

    write_file(path, buffer.getvalue(), overwrite=True)