from __future__ import annotations
from enum import Enum
from fastapi import APIRouter, FastAPI
from pydantic import BaseModel, Field
import os
from typing import Optional
from google import genai
from google.genai import types

router = APIRouter(prefix="/ai", tags=["ai"])


# -----------------------------
# Enums
# -----------------------------
class StudyType(str, Enum):
    memorization = "memorization"        # 암기형
    comprehension = "comprehension"      # 이해형
    problem_solving = "problem_solving"  # 문제풀이형
    practice = "practice"                # 실습형


class SessionType(str, Enum):
    study = "study"
    short_break = "short_break"
    long_break = "long_break"


class RecommendationFit(str, Enum):
    exact = "exact"    # 목표 시간과 정확히 일치
    under = "under"    # 목표 시간보다 조금 짧음 (최대 -10분)
    over = "over"      # 목표 시간보다 조금 김 (최대 +20분)


# -----------------------------
# Rules
# -----------------------------
# 공부 유형별 기본 포모도로 규칙
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
MAX_SESSIONS = 13        # 최대 세션 수


# -----------------------------
# Request / Response Models
# -----------------------------
class StudyPlanRequest(BaseModel):
    study_type: StudyType = Field(..., description="공부 유형")
    total_study_minutes: int = Field(..., ge=30, le=480, description="총 학습 시간(휴식 포함)")


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
    ai_message: str


# -----------------------------
# Helper Functions
# -----------------------------
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


def calculate_total_minutes(
    study_type: StudyType,
    study_minutes: int,
    short_break_minutes: int,
    num_sessions: int,
    include_long_break: bool,
) -> int:
    total = (study_minutes + short_break_minutes) * num_sessions
    cycle_sessions = BASE_RULES[study_type]["cycle_sessions"]

    # 긴 휴식은 사이클을 초과하는 세션이 있을 때만 1번 추가
    if include_long_break and num_sessions > cycle_sessions:
        total += LONG_BREAK_MINUTES

    return total


def can_include_long_break(study_type: StudyType, num_sessions: int) -> bool:
    cycle_sessions = BASE_RULES[study_type]["cycle_sessions"]
    return num_sessions > cycle_sessions


def fit_type_from_difference(diff: int) -> RecommendationFit:
    if diff == 0:
        return RecommendationFit.exact
    if diff < 0:
        return RecommendationFit.under
    return RecommendationFit.over


def title_from_fit(fit_type: RecommendationFit) -> str:
    return {
        RecommendationFit.exact: "설정 시간에 딱 맞는 추천",
        RecommendationFit.under: "조금 짧지만 부담이 적은 추천",
        RecommendationFit.over: "조금 길지만 흐름이 좋은 추천",
    }[fit_type]


def make_candidate_recommendations(study_type: StudyType, target_minutes: int) -> list[PlanRecommendation]:
    """
    RECOMMENDATION_PATTERNS의 모든 패턴 × 세션 수 1~13 × 긴휴식 포함/미포함
    조합으로 후보 전체를 생성한다. 중복은 seen_signatures로 걸러낸다.
    """
    candidates: list[PlanRecommendation] = []
    seen_signatures: set[tuple] = set()

    for pattern in RECOMMENDATION_PATTERNS[study_type]:
        study_minutes = pattern["study"]
        short_break_minutes = pattern["break"]
        pattern_label = pattern["label"]

        for num_sessions in range(1, MAX_SESSIONS + 1):
            # 긴 휴식 없는 버전
            total_without_long = calculate_total_minutes(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                include_long_break=False,
            )
            diff_without_long = total_without_long - target_minutes
            sig_without = (study_minutes, short_break_minutes, num_sessions, False, total_without_long)

            if sig_without not in seen_signatures:
                schedule = build_schedule(
                    study_type=study_type,
                    study_minutes=study_minutes,
                    short_break_minutes=short_break_minutes,
                    num_sessions=num_sessions,
                    include_long_break=False,
                )
                candidates.append(
                    PlanRecommendation(
                        rank=0,
                        fit_type=fit_type_from_difference(diff_without_long),
                        title=title_from_fit(fit_type_from_difference(diff_without_long)),
                        pattern_label=pattern_label,
                        study_minutes=study_minutes,
                        short_break_minutes=short_break_minutes,
                        total_minutes=total_without_long,
                        difference_minutes=diff_without_long,
                        long_break_included=False,
                        schedule=schedule,
                    )
                )
                seen_signatures.add(sig_without)

            # 긴 휴식 포함 버전
            if can_include_long_break(study_type, num_sessions):
                total_with_long = calculate_total_minutes(
                    study_type=study_type,
                    study_minutes=study_minutes,
                    short_break_minutes=short_break_minutes,
                    num_sessions=num_sessions,
                    include_long_break=True,
                )
                diff_with_long = total_with_long - target_minutes
                sig_with = (study_minutes, short_break_minutes, num_sessions, True, total_with_long)

                if sig_with not in seen_signatures:
                    schedule = build_schedule(
                        study_type=study_type,
                        study_minutes=study_minutes,
                        short_break_minutes=short_break_minutes,
                        num_sessions=num_sessions,
                        include_long_break=True,
                    )
                    candidates.append(
                        PlanRecommendation(
                            rank=0,
                            fit_type=fit_type_from_difference(diff_with_long),
                            title=title_from_fit(fit_type_from_difference(diff_with_long)),
                            pattern_label=pattern_label,
                            study_minutes=study_minutes,
                            short_break_minutes=short_break_minutes,
                            total_minutes=total_with_long,
                            difference_minutes=diff_with_long,
                            long_break_included=True,
                            schedule=schedule,
                        )
                    )
                    seen_signatures.add(sig_with)

    return candidates


def is_one_recommendation_case(study_type: StudyType, target_minutes: int) -> PlanRecommendation | None:
    """
    목표 시간이 기본 리듬으로 정확히 나누어 떨어지는 경우 바로 반환 (early return)

    경우 A: 기본 세션 반복만으로 딱 맞음
    경우 B: 기본 사이클 + 긴 휴식 + 추가 세션으로 딱 맞음
    """
    rule = BASE_RULES[study_type]
    study_minutes = rule["study_minutes"]
    short_break_minutes = rule["short_break_minutes"]
    cycle_sessions = rule["cycle_sessions"]

    session_total = study_minutes + short_break_minutes

    # 경우 A
    if target_minutes % session_total == 0:
        num_sessions = target_minutes // session_total
        if 1 <= num_sessions <= MAX_SESSIONS:
            schedule = build_schedule(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                include_long_break=False,
            )
            return PlanRecommendation(
                rank=1,
                fit_type=RecommendationFit.exact,
                title=title_from_fit(RecommendationFit.exact),
                pattern_label="기본 리듬",
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                total_minutes=target_minutes,
                difference_minutes=0,
                long_break_included=False,
                schedule=schedule,
            )

    # 경우 B
    cycle_total_with_long = (session_total * cycle_sessions) + LONG_BREAK_MINUTES
    remaining = target_minutes - cycle_total_with_long

    if remaining >= 0 and remaining % session_total == 0:
        extra_sessions = remaining // session_total
        num_sessions = cycle_sessions + extra_sessions

        if cycle_sessions < num_sessions <= MAX_SESSIONS:
            schedule = build_schedule(
                study_type=study_type,
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                num_sessions=num_sessions,
                include_long_break=True,
            )
            return PlanRecommendation(
                rank=1,
                fit_type=RecommendationFit.exact,
                title=title_from_fit(RecommendationFit.exact),
                pattern_label="기본 리듬",
                study_minutes=study_minutes,
                short_break_minutes=short_break_minutes,
                total_minutes=target_minutes,
                difference_minutes=0,
                long_break_included=True,
                schedule=schedule,
            )

    return None


# -----------------------------
# Core Logic
# -----------------------------

# 기본 리듬으로 딱 떨어지면 바로 반환
def generate_study_plan_options(study_type: StudyType, total_study_minutes: int) -> StudyPlanResponse:
    rule = get_base_rule(study_type)
    base_rule = BaseRule(
        study_minutes=rule["study_minutes"],
        short_break_minutes=rule["short_break_minutes"],
        session_total_minutes=rule["study_minutes"] + rule["short_break_minutes"],
        cycle_sessions=rule["cycle_sessions"],
        long_break_minutes=LONG_BREAK_MINUTES,
    )

    exact_one = is_one_recommendation_case(study_type, total_study_minutes)
    if exact_one is not None:
        recommendations = [exact_one]
        summary = f"{rule['label']} 기본 리듬으로 자연스럽게 맞는 추천 1개를 제공했어요."
        ai_message = generate_ai_message(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            recommendations=recommendations,
        )
        return StudyPlanResponse(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            base_rule=base_rule,
            recommendations=recommendations,
            summary=summary,
            ai_message=ai_message,
        )

    candidates = make_candidate_recommendations(study_type, total_study_minutes)

    exact_candidates = [c for c in candidates if c.difference_minutes == 0]
    under_candidates = [c for c in candidates if 0 > c.difference_minutes >= -UNDER_LIMIT]
    over_candidates = [c for c in candidates if 0 < c.difference_minutes <= OVER_LIMIT]

    exact_candidates.sort(key=lambda x: (x.total_minutes, x.study_minutes))
    under_candidates.sort(key=lambda x: (abs(x.difference_minutes), x.total_minutes))
    over_candidates.sort(key=lambda x: (x.difference_minutes, x.total_minutes))

    recommendations: list[PlanRecommendation] = []
    used_signatures: set[tuple] = set()

    for group in (exact_candidates[:1], under_candidates[:1], over_candidates[:1]):
        for item in group:
            sig = (
                item.study_minutes,
                item.short_break_minutes,
                item.total_minutes,
                item.long_break_included,
            )
            if sig not in used_signatures:
                recommendations.append(item)
                used_signatures.add(sig)

    for idx, recommendation in enumerate(recommendations, start=1):
        recommendation.rank = idx

    summary = f"{rule['label']} 공부에 맞춰 딱 맞는 안, 조금 짧은 안, 조금 긴 안 중 가능한 추천을 골라드렸어요."
    ai_message = generate_ai_message(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        recommendations=recommendations,
    )

    return StudyPlanResponse(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        base_rule=base_rule,
        recommendations=recommendations,
        summary=summary,
        ai_message=ai_message,
    )


def _format_recommendations_for_prompt(recommendations: list[PlanRecommendation]) -> str:
    lines = []

    for rec in recommendations:
        lines.append(
            (
                f"- rank={rec.rank}, "
                f"fit_type={rec.fit_type.value}, "
                f"title={rec.title}, "
                f"pattern_label={rec.pattern_label}, "
                f"study={rec.study_minutes}분, "
                f"short_break={rec.short_break_minutes}분, "
                f"total={rec.total_minutes}분, "
                f"difference={rec.difference_minutes}분, "
                f"long_break_included={rec.long_break_included}"
            )
        )

    return "\n".join(lines)


def generate_ai_message(
    study_type: StudyType,
    total_study_minutes: int,
    recommendations: list[PlanRecommendation],
    model_name: str = "gemini-3-flash-preview",
) -> str:
    """
    규칙 기반 추천 결과를 바탕으로 Gemini가 사용자용 설명/격려 메시지를 생성한다.
    실패하면 규칙 기반 fallback 메시지를 반환한다.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return build_fallback_ai_message(
            study_type=study_type,
            total_study_minutes=total_study_minutes,
            recommendations=recommendations,
        )

    if not recommendations:
        return "추천 가능한 학습 플랜을 정리하는 중이에요. 잠시 후 다시 시도해 주세요."

    study_type_label = BASE_RULES[study_type]["label"]
    recommendation_text = _format_recommendations_for_prompt(recommendations)

    system_instruction = (
        "당신은 포모도로 학습 도우미 AI입니다. "
        "항상 한국어로 답하세요. "
        "말투는 친절하고 간결하게 유지하세요. "
        "사용자에게 너무 장황하지 않게 3~5문장으로 답하세요. "
        "반드시 아래 규칙을 지키세요:\n"
        "1. 추천 결과를 왜 제안했는지 쉽게 설명할 것\n"
        "2. 가장 적합한 추천 1개를 자연스럽게 강조할 것\n"
        "3. 부담을 줄이는 짧은 격려 문장 1개를 포함할 것\n"
        "4. 존재하지 않는 시간이나 일정을 지어내지 말 것\n"
        "5. recommendations에 있는 정보만 사용해서 설명할 것"
    )

    user_prompt = f"""
사용자 공부 유형: {study_type_label}
사용자 총 학습 시간: {total_study_minutes}분

추천 목록:
{recommendation_text}

위 추천 목록을 바탕으로 사용자에게 보여줄 안내 메시지를 작성하세요.

출력 조건:
- 한국어
- 3~5문장
- 첫 문장에서는 전체 추천 방향을 설명
- 둘째 문장에서는 가장 적합한 추천 1개를 자연스럽게 강조
- 셋째 문장 이후에는 휴식 리듬 또는 집중 흐름의 장점을 설명
- 마지막 문장에는 짧은 격려 추가
- 마크다운 금지
- 번호 목록 금지
""".strip()

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=220,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )

        text = (response.text or "").strip()
        if text:
            return text

    except Exception:
        pass

    return build_fallback_ai_message(
        study_type=study_type,
        total_study_minutes=total_study_minutes,
        recommendations=recommendations,
    )    


def build_fallback_ai_message(
    study_type: StudyType,
    total_study_minutes: int,
    recommendations: list[PlanRecommendation],
) -> str:
    """
    Gemini 호출 실패 시 사용할 규칙 기반 메시지
    """
    label = BASE_RULES[study_type]["label"]

    if not recommendations:
        return f"{label} 공부에 맞는 학습 플랜을 다시 계산해 보세요."

    top = recommendations[0]

    fit_text_map = {
        "exact": "설정한 시간에 딱 맞는 흐름",
        "under": "조금 짧지만 부담이 적은 흐름",
        "over": "조금 길지만 집중 흐름이 좋은 구성",
    }

    fit_text = fit_text_map.get(top.fit_type.value, "균형 잡힌 학습 흐름")

    return (
        f"{label} 공부에는 {fit_text}이 잘 맞아요. "
        f"이번 추천에서는 {top.study_minutes}분 공부와 "
        f"{top.short_break_minutes}분 휴식 리듬을 기준으로 구성했어요. "
        f"너무 무리하지 말고 한 세션씩 차분히 해보세요."
    )





# -----------------------------
# Router endpoints
# -----------------------------
@router.get("", summary="AI 서비스 상태 확인")
def ai_root() -> dict[str, str]:
    return {"message": "AI service is running"}


@router.post("/study-plan-options", response_model=StudyPlanResponse, summary="포모도로 플랜 추천 생성")
def create_study_plan(request: StudyPlanRequest) -> StudyPlanResponse:
    return generate_study_plan_options(
        study_type=request.study_type,
        total_study_minutes=request.total_study_minutes,
    )


# -----------------------------
# Standalone app (로컬 테스트용)
# uvicorn ai_service:app --reload
# -----------------------------
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Pomodoro AI Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 테스트용. 나중에는 프론트 주소만 허용하는 것이 좋음
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Pomodoro AI Service"}