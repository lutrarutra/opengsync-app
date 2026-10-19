import secrets

import sqlalchemy as sa
from sqlalchemy import sql

from ..models import User, APIToken
from ..core import utils

def create(
    owner: User,
    time_valid_min: int,
) -> APIToken:
    """Create a token with a fresh secret. Only its hash is stored; the secret is on
    ``.plaintext`` of the returned object and must be shown to the user now."""
    plaintext = secrets.token_urlsafe(32)
    token = APIToken(
        owner=owner,
        time_valid_min=time_valid_min,
        token_hash=APIToken.hash(plaintext),
    )
    token.plaintext = plaintext
    return token


def search(
    owner_name: str | None = None,
    statement: sa.Select[tuple[APIToken]] = sa.select(APIToken),
) -> sa.Select[tuple[APIToken]]:
    """Fuzzy search on the owner's full name."""
    if owner_name is None:
        return statement

    full_name = User.name.expression
    return statement.join(User, APIToken.owner_id == User.id).where(
        utils.safe_trgm_search(full_name, owner_name)
    ).order_by(sa.func.similarity(full_name, owner_name).desc())


def select(
    id: int | None = None,
    token: str | None = None,
    owner_id: int | None = None,
    statement: sql.Select[tuple[APIToken]] = sa.select(APIToken),
) -> sql.Select[tuple[APIToken]]:
    statement = statement.where(*where_clauses(
        id=id, token=token,
        owner_id=owner_id,
    ))
    return statement


def where_clauses(
    id: int | None = None,
    token: str | None = None,
    owner_id: int | None = None,
) -> list[sa.ColumnElement[bool]]:
    """Return WHERE clauses for filtering API tokens.
    Reusable in correlated subqueries where .subquery() would break correlation.
    """
    clauses: list[sa.ColumnElement[bool]] = []

    if id is not None:
        clauses.append(APIToken.id == id)
    if token is not None:
        clauses.append(APIToken.token_hash == APIToken.hash(token))
    if owner_id is not None:
        clauses.append(APIToken.owner_id == owner_id)

    return clauses