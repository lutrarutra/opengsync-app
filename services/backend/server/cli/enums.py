import argparse
import enum
import inspect
import json
import importlib.util
import sys
from pathlib import Path

def load_module_from_path(file_path: Path):
    """Dynamically imports a python file from a disk path."""
    module_name = file_path.stem
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        print(f"Error: Could not load file at {file_path}")
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

def generate_ts_content(module):
    """Scans a module for Enums and returns TypeScript + Zod code."""
    output = [
        "// AUTO-GENERATED FILE - DO NOT EDIT MANUALLY",
        "import { z } from 'zod';\n"
    ]

    enums = [
        obj for name, obj in inspect.getmembers(module)
        if inspect.isclass(obj) and issubclass(obj, enum.Enum) and obj != enum.Enum
    ]

    for e in enums:
        name = e.__name__
        mapping = {m.name: m.value for m in e}

        output.append(f"export const {name} = {json.dumps(mapping, indent=2)} as const;")
        output.append(f"export type {name} = (typeof {name})[keyof typeof {name}];")
        output.append(f"export const {name}Schema = z.enum({name});")

        options = [
            {"label": m.name.replace("_", " ").title(), "value": m.value}
            for m in e
        ]
        output.append(f"export const {name}Options = {json.dumps(options, indent=2)} as const;\n")

    return "\n".join(output)

def main():
    parser = argparse.ArgumentParser(description="Translate Python Enums to TypeScript.")
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the Python file containing Enums."
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Path where the TypeScript file should be saved."
    )

    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file {input_path} does not exist.")
        sys.exit(1)

    module = load_module_from_path(input_path)
    ts_code = generate_ts_content(module)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(ts_code)
    print(f"✅ Successfully translated enums from {input_path} to {output_path}")

if __name__ == "__main__":
    main()
