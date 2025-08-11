import os
from typing import Optional
from datetime import datetime
import json  # Add this import

DEFAULT_FMT = """{time}:
------------------------ [BEGIN LOG] ------------------------

{message}
------------------------ [ END LOG ] ------------------------
"""


class LogBuffer:
    def __init__(
        self,
        stdout: bool = True,
        log_dir: Optional[str] = None,
    ):
        self.stdout = stdout
        self.log_dir = log_dir
        self.buffer: list[str] | None = None
        self.src_prefix = os.path.dirname(os.path.abspath(__file__)).removesuffix("/opengsync_server/core")
        print(f"LogBuffer initialized with src_prefix: {self.src_prefix}", flush=True)

    def write(self, message: str):
        """Handle both serialized and non-serialized messages"""
        if self.buffer is not None:
            self.buffer.append(message)
        else:
            self.buffer = [message]
            self.flush()

    def start(self):
        """Enable buffering."""
        self.buffer = []

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
            message="".join(formatted_messages),  # Combine with origins
        )
        
        if self.stdout:
            print(log, flush=True)

        if self.log_dir:
            log_path = os.path.join(
                self.log_dir,
                datetime.now().strftime("%Y-%m-%d_server") + ".log",
            )
            err_path = os.path.join(
                self.log_dir,
                datetime.now().strftime("%Y-%m-%d_server") + ".err",
            )
            with open(log_path, "a") as f:
                f.write(log)
            with open(err_path, "a") as f:
                f.write(log)
        
        self.buffer = None


def create_buffer(
    stdout: bool = True, log_dir: str = "logs/"
) -> LogBuffer:
    log_buffer = LogBuffer(stdout=stdout, log_dir=log_dir)
    return log_buffer


log_buffer = create_buffer(stdout=True)