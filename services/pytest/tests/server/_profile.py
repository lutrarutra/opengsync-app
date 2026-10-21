"""Organization/PI fields of user forms (server/forms/common/UserProfileMixin.py): payloads and stored values."""
from opengsync_db import SyncSession, models

INSTITUTE = "Medical University of Vienna"
DEPARTMENT = "Department of Medicine I"
PI_NAME = "Grace Hopper"
PI_EMAIL = "grace.hopper@example.com"


def new_profile_payload(
    institute: str = INSTITUTE, department: str = DEPARTMENT, pi_name: str = PI_NAME, pi_email: str = PI_EMAIL,
    prefix: str = "",
) -> dict[str, str]:
    """All four values typed as new ones."""
    return {
        f"{prefix}institute": "new", f"{prefix}institute-text": institute,
        f"{prefix}department": "new", f"{prefix}department-text": department,
        f"{prefix}pi": "new", f"{prefix}pi-text": pi_name,
        f"{prefix}pi_email": pi_email,
    }


def set_profile(
    session: SyncSession, user: models.User,
    institute: str | None = INSTITUTE, department: str | None = DEPARTMENT,
    pi_name: str | None = PI_NAME, pi_email: str | None = PI_EMAIL,
) -> models.User:
    user.institute, user.department, user.pi_name, user.pi_email = institute, department, pi_name, pi_email
    session.flush()
    return user
