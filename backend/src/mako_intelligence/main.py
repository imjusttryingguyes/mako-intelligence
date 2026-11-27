from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mako_intelligence.api.routes.auth import router as auth_router
from mako_intelligence.api.routes.direct_bindings import router as direct_binding_router
from mako_intelligence.api.routes.health import router as health_router
from mako_intelligence.api.routes.projects import router as project_router
from mako_intelligence.core.config import frontend_origin

app = FastAPI(
    title="MAKO Intelligence API",
    version="0.1.0",
    description="Local-only Milestone B2 login and project overview. Not production-ready.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(direct_binding_router)
