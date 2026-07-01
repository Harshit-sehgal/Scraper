"""Session domain models — session create/destroy/me response models."""

from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    """Response model for POST /api/session."""

    status: str
    role: str
    message: str
    authenticated: bool = True


class SessionDestroyResponse(BaseModel):
    """Response model for DELETE /api/session."""

    status: str
    message: str


class SessionMeResponse(BaseModel):
    """Response model for GET /api/session/me."""

    authenticated: bool
    role: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    project_id: str | None = None
