from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.session import get_db

app = FastAPI(title="Tickets API", version="0.1.0")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/db-ping")
async def db_ping(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT 1"))
    return {"result": result.scalar_one()}
