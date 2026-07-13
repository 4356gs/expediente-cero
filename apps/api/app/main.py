"""FastAPI application entry point."""

from fastapi import FastAPI

from app import __version__
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API application without performing external I/O."""
    resolved_settings = settings or get_settings()
    docs_url = "/docs" if resolved_settings.api_docs_enabled else None
    openapi_url = "/openapi.json" if resolved_settings.api_docs_enabled else None

    application = FastAPI(
        title="Expediente Cero API",
        description="Backend for synthetic, human-reviewed intake preparation.",
        version=__version__,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
    )
    application.state.settings = resolved_settings
    application.include_router(health_router)
    return application


app = create_app()
