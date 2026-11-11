"""Liveness probe.

Mounted at `/api/v1/health/` — a stable, dependency-free path the AWS ALB
target group can probe. Keep it free of DB/redis calls so a slow dependency
cannot make healthy tasks get deregistered.
"""

from fastapi import APIRouter

from app.models import Envelope, Message

router = APIRouter(tags=["health"])


@router.get(
    "/",
    response_model=Envelope[Message],
    summary="Liveness probe",
    responses={200: {"description": "The process is up"}},
)
def health_check() -> Envelope[Message]:
    return Envelope(data=Message(message="ok"))
