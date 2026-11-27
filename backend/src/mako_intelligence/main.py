from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mako_intelligence.api.routes.health import router as health_router
from mako_intelligence.core.config import frontend_origin

app = FastAPI(
    title="MAKO Intelligence API",
    version="0.1.0",
    description="Milestone A scaffold. No customer data or ad account access.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin()],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
