import os
from datetime import datetime
from pathlib import Path
import json

DEFAULT_FMT = """{time}:
------------------------ [ BEGIN: {session_name} ] ------------------------

{message}------------------------ [ END: {session_name} ] ------------------------
"""


class LogBuffer:
    log_dir: Path | None

    def __init__(self, debug: bool = False):
        self.log_dir = None
        self.buffer: list[str] | None = None
        self.session_name: str | None = None
        self.src_prefix = os.path.dirname(os.path.abspath(__file__)).removesuffix("/opengsync_server/core")
        self.debug = debug

    def set_log_dir(self, log_dir: Path, debug: bool = False):
        self.log_dir = log_dir
        self.debug = debug
        print(f"LogBuffer initialized with src_prefix: {self.src_prefix}", flush=True)
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

    def parse_record(self, record: dict) -> tuple[str, str]:
        text = record.get("text", "")
        metadata = record.get("record", {})
        level_name = metadata.get("level", {}).get("name", "INFO").upper()
        loc = ""
        if (file := metadata.get("file", {}).get("path")):
            rel_file = file.removeprefix(self.src_prefix).lstrip('/')
            if (line := metadata.get("line")):
                loc = f"{rel_file}:{line}"
            else:
                loc = f"{rel_file}"
            
        msg = f"[{level_name} {loc}] >\n{text}\n"
        return msg, level_name
        
    def flush(self):
        """Flush buffered logs with per-message origins and level support."""
        if not self.buffer:
            return
        
        formatted_messages = []
        info_buffer = []
        error_buffer = []
        for record_str in self.buffer:
            try:
                record = json.loads(record_str)
                parsed_msg, level_name = self.parse_record(record)
                formatted_messages.append(parsed_msg)
                
                if level_name in ("INFO", "WARNING"):
                    info_buffer.append(parsed_msg)
                elif level_name in ("ERROR", "CRITICAL"):
                    error_buffer.append(parsed_msg)
                else:
                    info_buffer.append(parsed_msg)
            except json.JSONDecodeError:
                unknown_msg = f"[<unknown origin>]:\n{record_str}\n"
                formatted_messages.append(unknown_msg)
                info_buffer.append(unknown_msg)
        
        all_logs = "".join(formatted_messages)

        log = DEFAULT_FMT.format(
            time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            message=all_logs,
            session_name=self.session_name or "request"
        )
        
        if self.debug:
            print(log, flush=True)
        else:
            if (error_message := "".join(error_buffer)).strip():
                error_log = DEFAULT_FMT.format(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    message=error_message,
                    session_name=self.session_name or "request"
                )
                print(error_log, flush=True)
        
        if self.log_dir:
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_path = self.log_dir / f"{date_str}.log"
            err_path = self.log_dir / f"{date_str}.err"
            
            if info_buffer:
                info_log = DEFAULT_FMT.format(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    message="".join(info_buffer),
                    session_name=self.session_name or "request"
                )
                with open(log_path, "a") as f:
                    f.write(info_log)
            
            if error_buffer:
                err_log = DEFAULT_FMT.format(
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    message="".join(error_buffer),
                    session_name=self.session_name or "request"
                )
                with open(err_path, "a") as f:
                    f.write(err_log)
        
        self.buffer = None

    def __del__(self):
        if self.buffer is not None:
            self.flush()


log_buffer = LogBuffer()