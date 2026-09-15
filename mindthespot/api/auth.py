"""Authentication and user context extraction from Google Cloud Identity-Aware Proxy (IAP)."""

from fastapi import Request
from pydantic import BaseModel


class UserContext(BaseModel):
    """User identity context extracted from Cloud IAP headers or local development fallback."""

    email: str
    user_id: str | None = None
    is_authenticated: bool = False


def get_current_user_context(request: Request) -> UserContext:
    """Extract authenticated Google identity from Cloud IAP headers.

    When Cloud IAP is enabled, it injects:
    - X-Goog-Authenticated-User-Email: accounts.google.com:username@domain.com
    - X-Goog-Authenticated-User-Id: Unique account ID

    When running locally or in tests without IAP, returns a fallback development context.
    """
    raw_email = request.headers.get("x-goog-authenticated-user-email")
    raw_id = request.headers.get("x-goog-authenticated-user-id")

    if raw_email:
        # Strip GCP account namespace prefix e.g. "accounts.google.com:"
        email = raw_email.split(":")[-1] if ":" in raw_email else raw_email
        return UserContext(
            email=email,
            user_id=raw_id,
            is_authenticated=True,
        )

    return UserContext(
        email="dev@mindthespot.internal",
        user_id="local-dev",
        is_authenticated=False,
    )
