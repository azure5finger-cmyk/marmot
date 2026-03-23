from __future__ import annotations 
# 구버전 python에서  list[ScheduleItem], dict[StudyType, dict] 사용할 수 있게 해줌.
from enum import Enum

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field

router = APIRouter(prefix="/ai_service", tags=["ai_service"])

# Enums(enumerations)

class StudyType(str, Enum):                 # 학습유형 
    memorization = "memorization"           # 암기형
    comprehension = "comprehension"         # 이해형
    problem_solving = "problem_solving"     # 문제풀이형         
    practice = "practice"                   # 실습형

class SessionType(str, Enum):
    study = "study"
    short_break = "short_break"
    long_break = "long_break"

class RecommendationFit(str, Enum):
    exact = "exact"      # 목표 시간과 정확히 일치
    under = "under"      # 목표 시간보다 조금 짧음 (최대 -10분)
    over = "over"        # 목표 시간보다 조금 김 (최대 +20분)
    closest = "closest"  # exact/under/over 모두 없을 때 가장 가까운 후보


# Rules : StudyType별 기본 타이머 시간 규칙.

BASE_RULES: dict[StudyType, dict] = {
    StudyType.memorization: {
        "label": "암기형",
        "study_minutes": 25,
        "short_break_minutes": 5,
        "cycle_sessions": 4,   # 긴 휴식 전까지의 기본 세션 수
    },
    StudyType.comprehension: {
        "label": "이해형",
        "study_minutes": 40,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
    StudyType.problem_solving: {
        "label": "문제풀이형",
        "study_minutes": 50,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
    StudyType.practice: {
        "label": "실습형",
        "study_minutes": 50,
        "short_break_minutes": 10,
        "cycle_sessions": 2,
    },
}

# 공부 유형별 추천 패턴 후보 (기본 리듬 + 대안 2개)
# study + short_break = 세션 1개의 총 시간
RECOMMENDATION_PATTERNS: dict[StudyType, list[dict]] = {
    StudyType.memorization: [
        {"study": 25, "break": 5, "label": "기본 리듬"},
        {"study": 20, "break": 5, "label": "짧게 반복"},
        {"study": 30, "break": 5, "label": "조금 길게 집중"},
    ],
    StudyType.comprehension: [
        {"study": 40, "break": 10, "label": "기본 리듬"},
        {"study": 50, "break": 10, "label": "길게 이해"},
        {"study": 30, "break": 5,  "label": "짧게 읽기"},
    ],
    StudyType.problem_solving: [
        {"study": 50, "break": 10, "label": "기본 리듬"},
        {"study": 40, "break": 10, "label": "짧게 풀이"},
        {"study": 60, "break": 10, "label": "길게 몰입"},
    ],
    StudyType.practice: [
        {"study": 50, "break": 10, "label": "기본 리듬"},
        {"study": 40, "break": 10, "label": "짧게 실습"},
        {"study": 60, "break": 10, "label": "길게 몰입"},
    ],
}

LONG_BREAK_MINUTES = 20  # 긴 휴식 고정 시간 (분)
UNDER_LIMIT = 10         # under 허용 범위: 목표보다 최대 10분 짧은 것까지 허용
OVER_LIMIT = 20          # over  허용 범위: 목표보다 최대 20분 긴 것까지 허용

# Request, Response Models
class StudyPlanRequest(BaseModel):
    study_type: StudyType = Field(..., description="공부 유형")
    total_study_minutes: int = Field(..., ge=30, le=720, description="총 학습 시간(휴식 포함)")


class BaseRule(BaseModel):
    study_minutes: int
    short_break_minutes: int
    session_total_minutes: int   # study + short_break (세션 1개 총 시간)
    cycle_sessions: int          # 긴 휴식 전까지의 세션 수
    long_break_minutes: int


class ScheduleItem(BaseModel):
    order: int
    type: SessionType
    minutes: int
    label: str


class PlanRecommendation(BaseModel):
    rank: int
    fit_type: RecommendationFit
    title: str
    pattern_label: str
    study_minutes: int
    short_break_minutes: int
    total_minutes: int
    difference_minutes: int      # total_minutes - target_minutes (음수면 under, 양수면 over)
    long_break_included: bool
    schedule: list[ScheduleItem]


class StudyPlanResponse(BaseModel):
    study_type: StudyType
    total_study_minutes: int
    base_rule: BaseRule
    recommendations: list[PlanRecommendation]
    summary: str


# Helper Functions
def get_base_rule(study_type: StudyType) -> dict:
    return BASE_RULES[study_type]


def build_schedule(
    study_type: StudyType,
    study_minutes: int,
    short_break_minutes: int,
    num_sessions: int,
    include_long_break: bool,
) -> list[ScheduleItem]:
    label = BASE_RULES[study_type]["label"]
    cycle_sessions = BASE_RULES[study_type]["cycle_sessions"]
    schedule: list[ScheduleItem] = []

    for i in range(1, num_sessions + 1):
        schedule.append(
            ScheduleItem(
                order=len(schedule) + 1,
                type=SessionType.study,
                minutes=study_minutes,
                label=f"{label} 세션 {i}",
            )
        )
        schedule.append(
            ScheduleItem(
                order=len(schedule) + 1,
                type=SessionType.short_break,
                minutes=short_break_minutes,
                label="짧은 휴식",
            )
        )

        # cycle_sessions 번째 세션 직후에만 긴 휴식 삽입
        # (마지막 세션 뒤에는 넣지 않음 → i < num_sessions 조건)
        # cycle 뒤의 짧은 휴식은 이미 위에서 추가했으므로 긴 휴식만 추가
        if include_long_break and i == cycle_sessions and i < num_sessions:
            schedule.append(
                ScheduleItem(
                    order=len(schedule) + 1,
                    type=SessionType.long_break,
                    minutes=LONG_BREAK_MINUTES,
                    label="긴 휴식",
                )
            )

    return schedule
