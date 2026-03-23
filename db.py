from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, Text, Date, DateTime, ForeignKey 
from sqlalchemy.sql import func  
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# 비동기 엔진
engine = create_async_engine(DATABASE_URL, echo=True)

# 비동기 세션
SessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False
)

# Base 클래스
Base = declarative_base()

# 의존성 주입용
async def get_db():
    async with SessionLocal() as db:
        yield db

# 모델 클래스들
class User(Base):                                                 # 유저 테이블
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(100))
    password = Column(String(200))
    nickname = Column(String(50))
    goal_minutes = Column(Integer, default=120)
    default_focus_time = Column(Integer, default=25)
    default_break_time = Column(Integer, default=5)
    ai_mode = Column(String(20))
    created_at = Column(DateTime, default=func.now())

class PomodoroSession(Base):                                     # 포모도로 세션 테이블
    __tablename__ = "pomodoro_sessions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    total_duration = Column(Integer, default=0)

class SessionDetail(Base):                                       # 세션 상세 테이블
    __tablename__ = "session_details"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("pomodoro_sessions.id"))
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration = Column(Integer)
    is_completed = Column(Boolean, default=False)
    session_type = Column(String(10))

class Memo(Base):                                                # 메모 테이블
    __tablename__ = "memos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(Text)
    content = Column(Text)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now())

class Todo(Base):                                                # 투두 테이블
    __tablename__ = "todos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    content = Column(Text)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

class StudyRecord(Base):                                         # 공부기록 테이블
    __tablename__ = "study_records"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    total_minutes = Column(Integer, default=0)
    completed_sessions = Column(Integer, default=0)
    goal_achieved = Column(Boolean, default=False)

class AiLog(Base):                                              # AI 로그 테이블
    __tablename__ = "ai_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    message = Column(Text)
    mode = Column(String(20))
    created_at = Column(DateTime, default=func.now())
