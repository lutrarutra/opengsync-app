from itsdangerous import URLSafeTimedSerializer


def generate_file_share_token(path: str, serializer: URLSafeTimedSerializer) -> str:
    return str(serializer.dumps({"path": path}))


def verify_file_share_token(token: str, max_age_hours: int, serializer: URLSafeTimedSerializer) -> str | None:
    data = serializer.loads(token, max_age=max_age_hours * 60 * 60)
    return data.get("path")