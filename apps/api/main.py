from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.config import settings
from apps.api.core.db import check_db_connection
from apps.api.routers import auth, checkin, homework, items, notes, progress, sources, study

app = FastAPI(title="NeuroAI Study Kit API")

# The regex covers local dev — Vite picks the next free port (5173, 5174, ...) when 5173 is
# taken, so a fixed origin wouldn't do. `web_origin` (M13, settings.web_origin) covers the
# deployed frontend in production; CORSMiddleware allows a request that matches either.
# allow_credentials so the browser sends/accepts the Authorization header cross-origin — no
# API key or other secret ever crosses this either way, see CLAUDE.md invariant 3.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin] if settings.web_origin else [],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(study.router)
app.include_router(items.router)
app.include_router(sources.router)
app.include_router(homework.router)
app.include_router(notes.router)
app.include_router(progress.router)
app.include_router(checkin.router)


@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = await check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "error"}
