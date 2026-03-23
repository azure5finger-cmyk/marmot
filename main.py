from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import RedirectResponse
from contextlib import asynccontextmanager
from fastapi.templating import Jinja2Templates
import ai_service, calendar, db, timer, user, stats


@asynccontextmanager
async def app_life_span(app: FastAPI):
    async with db.engine.begin() as conn:                  # 종료하면 자동으로 닫힌다.
        await conn.run_sync(db.Base.metadata.create_all)   # 동기 실행 ==> 비동기 실행.
    yield    

app = FastAPI(lifespan=app_life_span)

app.include_router(timer.router)
app.include_router(calendar.router)
app.include_router(ai_service.router)
app.include_router(user.router)
app.include_router(stats.router)
app.include_router(stats.stats_router)

@app.get("/")
async def root():
    return RedirectResponse(url="/timer")