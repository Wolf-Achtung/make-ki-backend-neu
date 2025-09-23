from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.config import settings
from services.logging_setup import configure_logging
from app.routers import health, report

configure_logging()

app = FastAPI(
    title="KI-Status-Report Backend",
    version="1.0.0",
    description="Gold-Standard Backend für DE/EN Reports inkl. Prompts, Data, Tavily-News und optionalem PDF-Export."
)

# CORS
origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")] if settings.ALLOWED_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="")
app.include_router(report.router, prefix="/api")

# Uvicorn entry (optional)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=(settings.APP_ENV != "production"))
