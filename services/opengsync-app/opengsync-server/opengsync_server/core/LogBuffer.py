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
        log_path: Optional[str] = None,
        err_path: Optional[str] = None,
    ):
        self.stdout = stdout
        self.log_path = log_path
        self.err_path = err_path
        self.buffer: list[str] | None = None
        self.src_prefix = os.path.dirname(os.path.abspath(__file__)).removesuffix("/opengsync_server/core")
        print(f"LogBuffer initialized with src_prefix: {self.src_prefix}", flush=True)

    def write(self, message: str):
        """Handle both serialized and non-serialized messages"""
        if self.buffer is not None:
            self.buffer.append(message)
        else:
            # Immediate logging (non-buffered)
            try:
                record = json.loads(message)
                message = self.parse_record(record)
                message = DEFAULT_FMT.format(
                    level="INFO",
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    message="".join(message),  # Combine with origins
                )
                print(message, flush=True)
            except json.JSONDecodeError:
                message = DEFAULT_FMT.format(
                    level="ERROR",
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    message="".join(message),  # Combine with origins
                )
                print(message, flush=True)  # Fallback for non-serialized messages

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
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(log)
        if self.err_path:
            with open(self.err_path, "a") as f:
                f.write(log)
        
        self.buffer = None


def create_buffer(
    stdout: bool = True, log_path: Optional[str] = None, err_path: Optional[str] = None
) -> LogBuffer:
    log_buffer = LogBuffer(stdout=stdout, log_path=log_path, err_path=err_path)
    return log_buffer


log_buffer = create_buffer(stdout=True, log_path="opengsync.log", err_path="opengsync.err")