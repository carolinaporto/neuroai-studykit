from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.core.db import check_db_connection
from apps.api.routers import auth, homework, items, notes, progress, sources, study

app = FastAPI(title="NeuroAI Study Kit API")

# Dev-only: lets the Vite dev server (a different origin) call the API. Regex instead of a
# fixed port because Vite picks the next free one (5173, 5174, ...) when 5173 is taken.
# allow_credentials so the browser sends/accepts the session cookie cross-origin — no API
# key or other secret ever crosses this either way, see CLAUDE.md invariant 3.
app.add_middleware(
    CORSMiddleware,
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


@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = await check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "error"}
