from fastapi import APIRouter, Request, Depends
from fastapi import Form, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date
from .user import get_current_user, oauth2_scheme
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from .db import get_db, User

router = APIRouter()
templates = Jinja2Templates(directory="templates")

async def get_user_from_uid(
    token: str | None = Depends(oauth2_scheme), # 토큰 존재 여부 확인
    db: AsyncSession = Depends(get_db)
) -> User | None:
    # 토큰 자체가 없으면 바로 None 반환 (로그인 안 함)
    if not token:
        return None
        
    try:
        # 기존 user.py의 함수를 실행해서 user_id를 가져옴
        user_id = await get_current_user(token, db)
        
        # user_id로 DB에서 실제 유저 객체 조회
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalar_one_or_none()
        return user
        
    except HTTPException:
        # 토큰이 잘못되었거나 만료되어 401 에러가 발생하면 None 반환
        return None

@router.get("/timer")
async def timer(request:Request, current_user=Depends(get_user_from_uid),db: AsyncSession=Depends(get_db)):
    
    focus_time = current_user.default_focus_time if current_user else 25
    break_time = current_user.default_break_time if current_user else 5

    return templates.TemplateResponse("timer.html", {"request":request, "focus_time":focus_time, "break_time":break_time,})

@router.get("/timer/memo")
async def read_memo(request:Request, db: AsyncSession=Depends(get_db)):
    # TODO : 입력 된 메모 db에 넣어주는 자리
    pass
