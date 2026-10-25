from fastapi import APIRouter

from hypergolic.sessions.routes import context, lifecycle, listing, transcript

router = APIRouter()
for sub in (listing, lifecycle, transcript, context):
    router.include_router(sub.router, prefix="/api/sessions", tags=["sessions"])
