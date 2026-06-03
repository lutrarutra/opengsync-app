def json_encapsulate(key: str, value: str | bytes) -> bytes:
    return b'{"' + key.encode() + b'": ' + (value if isinstance(value, bytes) else value.encode()) + b'}'