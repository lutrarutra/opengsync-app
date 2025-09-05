import os
from datetime import datetime
from pathlib import Path
import json

DEFAULT_FMT = """{time}:
------------------------ [ BEGIN {session_name}] ------------------------

{message}
------------------------ [ END {session_name}] ------------------------
"""


class LogBuffer:
    log_dir: Path | None

    def __init__(
        self,
        stdout: bool = True,
    ):
        self.stdout = stdout
        self.log_dir = None
        self.buffer: list[str] | None = None
        self.session_name: str | None = None
        self.src_prefix = os.path.dirname(os.path.abspath(__file__)).removesuffix("/opengsync_server/core")
        print(f"LogBuffer initialized with src_prefix: {self.src_prefix}", flush=True)

    def set_log_dir(self, log_dir: Path):
        self.log_dir = log_dir
        if not self.log_dir.exists():
            os.makedirs(self.log_dir)

    def write(self, message: str):
        """Handle both serialized and non-serialized messages"""
        if self.buffer is not None:
            self.buffer.append(message)
        else:
            self.buffer = [message]
            self.flush()

    def start(self, name: str | None = None):
        """Enable buffering."""
        self.buffer = []
        self.session_name = name

    def parse_record(self, record: dict) -> str:
        text = record.get("text", "")
        metadata = record.get("record", {})
        loc = ""

        if (file := metadata.get("file", {}).get("path")):
            if (line := metadata.get("line")):
                loc = f" in {file.removeprefix(self.src_prefix).lstrip('/')}:{line}"

        fnc = metadata.get("module", "")
        fnc += (f".{metadata.get('function', '')}()").replace(".()", "")
            
        msg = f"[{fnc}:{loc}]\n{text}"
        return msg
    
    def flush(self):
        """Flush buffered logs with per-message origins."""
        if not self.buffer:
            return
        
        formatted_messages = []
        for record_str in self.buffer:
            try:
                record = json.loads(record_str)
                formatted_messages.append(self.parse_record(record))
            except json.JSONDecodeError:
                formatted_messages.append(f"[<unknown origin>]:\n{record_str}\n")
        
        log = DEFAULT_FMT.format(
            level="INFO",
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message="".join(formatted_messages),
            session_name=self.session_name or "unknown"
        )
        
        if self.stdout:
            print(log, flush=True)

        if self.log_dir:
            log_path = self.log_dir / (datetime.now().strftime("%Y-%m-%d") + ".log")
            err_path = self.log_dir / (datetime.now().strftime("%Y-%m-%d") + ".err")

            with open(log_path, "a") as f:
                f.write(log)
            with open(err_path, "a") as f:
                f.write(log)
        
        self.buffer = None


log_buffer = LogBuffer(stdout=True)