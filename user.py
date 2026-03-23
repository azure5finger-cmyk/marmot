from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
import os

from db import get_db_session, User

router = APIRouter(prefix="/users", tags=["users"])

SECRET_KEY = os.getenv("SECRET_KEY", "dev-fallback-key")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/login")


# --- Pydantic 스키마 ---

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    nickname: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class SettingsRequest(BaseModel):
    goal_minutes: int        # 단위: 분(minutes)
    default_focus_time: int  # 단위: 분(minutes)
    default_break_time: int  # 단위: 분(minutes)
    ai_mode: str


# --- 유틸 함수 ---

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_access_token(data: dict):
    to_encode = data.copy()
    # ISO 8601 형식으로 만료 시간 설정
    expire = datetime.now(timezone.utc) + timedelta(hours=2)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db_session)
):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return user_id


# --- 엔드포인트 ---

# 회원가입
@router.post("/signup")
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db_session)):

    result = await db.execute(select(User).filter(User.email == body.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already exists")

    new_user = User(
        email=body.email,
        password=hash_password(body.password),
        nickname=body.nickname
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {
        "message": "signup success",
        "user_id": new_user.id,
        # ISO 8601 형식으로 가입 시각 반환
        "created_at": new_user.created_at.isoformat()
    }


# 로그인
@router.post("/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db_session)):

    result = await db.execute(select(User).filter(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.password):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")

    token = create_access_token({"user_id": user.id})

    return {"access_token": token, "token_type": "bearer"}


# 마이페이지 조회
@router.get("/mypage")
async def mypage(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "email": user.email,
        "nickname": user.nickname,
        "goal_minutes": user.goal_minutes,        # 단위: 분(minutes)
        "default_focus_time": user.default_focus_time,  # 단위: 분(minutes)
        "default_break_time": user.default_break_time,  # 단위: 분(minutes)
        "ai_mode": user.ai_mode,
        # ISO 8601 형식으로 가입 시각 반환
        "created_at": user.created_at.isoformat()
    }


# 사용자 설정 수정
@router.put("/settings")
async def update_settings(
    body: SettingsRequest,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session)
):
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.goal_minutes = body.goal_minutes
    user.default_focus_time = body.default_focus_time
    user.default_break_time = body.default_break_time
    user.ai_mode = body.ai_mode

    await db.commit()

    return {"message": "settings updated"}