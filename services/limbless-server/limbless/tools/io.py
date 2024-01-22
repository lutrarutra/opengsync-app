import io
import os
import re
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
            logger.debug(f"Overwriting exising file: {path}")
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


def parse_config_tables(path: str, sep: Optional[str] = None) -> dict[str, pd.DataFrame]:
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
        matches = re.findall(r"\[(.*?)\]\n(.*?)(?=\n\[|$)", content, re.DOTALL)

        # Construct a dictionary where keys are labels and values are the corresponding strings
        result = dict()
        for label, text in matches:
            content = text.strip()
            if not content:
                result[label.strip()] = ""
            elif content.count(sep) > 0:
                result[label.strip()] = pd.read_csv(
                    io.StringIO(content), delimiter=sep, index_col=None, header=0,
                    comment="#"
                )
            else:
                result[label.strip()] = content

        return result


def write_config_tables_from_sections(path: str, sections: dict[str, pd.DataFrame], sep: Optional[str] = None, overwrite: bool = False):
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
        buffer.write(f"[{header}]\n")
        content.to_csv(buffer, index=False, sep=sep)
        buffer.write("\n\n")

    write_file(path, buffer.getvalue(), overwrite=overwrite)