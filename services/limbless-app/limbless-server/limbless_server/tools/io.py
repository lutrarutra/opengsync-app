import io
import os
import re
import yaml
import hashlib
from typing import Optional

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


def parse_config_tables(path: str, sep: Optional[str] = None) -> dict[str, pd.DataFrame | dict]:
    if sep is None:
        ext = path.split(".")[-1]
        if ext == "csv":
            sep = ","
        elif ext.split(".")[-1] == "tsv":
            sep = "\t"
        else:
            raise Exception(f"Could not infer separator from extension '.{ext}'. Specify it with 'sep'-parameter...")

    with open(path, "r") as f:
        content = f.read()

        # Construct a dictionary where keys are labels and values are the corresponding strings
        result = dict()

        matches = re.findall(r"\[(.*?)\]([yt])\n(.*?)(?=\n\[|$)", content, re.DOTALL)
        for label, type, text in matches:
            content = text.strip()
            if type == "y":
                result[label.strip()] = yaml.safe_load(io.StringIO(content))
            elif type == "t":
                result[label.strip()] = pd.read_csv(
                    io.StringIO(content), delimiter=sep, index_col=None, header=0,
                    comment="#"
                )
            else:
                raise Exception(f"Unsupported type: {type}, use 't' for table and 'y' for yaml...")

        return result


def write_config_tables_from_sections(path: str, sections: dict[str, pd.DataFrame | dict], sep: Optional[str] = None, overwrite: bool = False):
    if sep is None:
        ext = path.split(".")[-1]
        if ext == "csv":
            sep = ","
        elif ext.split(".")[-1] == "tsv":
            sep = "\t"
        else:
            raise Exception(f"Could not infer separator from extension '.{ext}'. Specify it with 'sep'-parameter...")

    buffer = io.StringIO()

    for header, content in sections.items():
        if isinstance(content, pd.DataFrame):
            buffer.write(f"[{header}]t\n")
            content.to_csv(buffer, index=False, sep=sep)
        elif isinstance(content, dict):
            buffer.write(f"[{header}]y\n")
            yaml.dump(content, buffer)
        else:
            raise TypeError(f"Unsupported type: {type(content)}")

        buffer.write("\n\n")

    write_file(path, buffer.getvalue(), overwrite=overwrite)