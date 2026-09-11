from fastapi import FastAPI

from apps.api.core.db import check_db_connection

app = FastAPI(title="NeuroAI Study Kit API")


@app.get("/health")
async def health() -> dict[str, str]:
    db_ok = await check_db_connection()
    return {"status": "ok", "db": "ok" if db_ok else "error"}
