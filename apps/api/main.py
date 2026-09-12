from fastapi import FastAPI

from apps.api.core.db import check_db_connection
from apps.api.routers import items, study

app = FastAPI(title="NeuroAI Study Kit API")
app.include_router(study.router)
app.include_router(items.router)


@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = await check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "error"}
