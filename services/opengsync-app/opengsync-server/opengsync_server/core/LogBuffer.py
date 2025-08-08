import sys

from typing import Any, Optional
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
    
    def write(self, message: str):
        """Handle both serialized and non-serialized messages"""
        if self.buffer is not None:
            self.buffer.append(message)
        else:
            # Immediate logging (non-buffered)
            try:
                record = json.loads(message)
                print(self._format_single(record))
            except json.JSONDecodeError:
                print(message)  # Fallback for non-serialized messages
    
    def start(self):
        """Enable buffering."""
        self.buffer = []

    def parse_record(self, record: dict) -> str:
        text = record.get("text", "")
        metadata = record.get("record", {})
        loc = ""

        if (file := metadata.get("file", {}).get("name")):
            if (line := metadata.get("line")):
                loc = f" in {file}:{line}"
            
        msg = f"[{metadata.get('module', '<module>')}.{metadata.get("function", "<function>")}:{loc}]\n{text}\n"
        return msg
    
    def _format_single(self, record: dict[str, Any]) -> str:
        """Format a single log record with origin info."""
        return self.parse_record(record)
    
    def _format_buffered(self, records: list[str]) -> str:
        """Format all buffered logs with origins."""
        formatted_messages = []
        for record_str in records:
            try:
                record = json.loads(record_str)
                formatted_messages.append(self.parse_record(record))
            except json.JSONDecodeError:
                formatted_messages.append(f"[<unknown origin>]:\n{record_str}\n")
        
        return DEFAULT_FMT.format(
            level="INFO",
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message="".join(formatted_messages),  # Combine with origins
        )
    
    def flush(self):
        """Flush buffered logs with per-message origins."""
        if not self.buffer:
            return
        
        log = self._format_buffered(self.buffer)
        
        if self.stdout:
            print(log)
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(log)
        if self.err_path:
            with open(self.err_path, "a") as f:
                f.write(log)
        
        self.buffer = None


def create_buffer(stdout: bool = True, log_path: Optional[str] = None, err_path: Optional[str] = None) -> LogBuffer:
    log_buffer = LogBuffer(stdout=stdout, log_path=log_path, err_path=err_path)
    
    def handle_crash(exc_type, exc_value, traceback):
        log_buffer.flush()
        sys.__excepthook__(exc_type, exc_value, traceback)

    sys.excepthook = handle_crash
    return log_buffer


log_buffer = create_buffer(stdout=True, log_path="opengsync.log", err_path="opengsync.err")