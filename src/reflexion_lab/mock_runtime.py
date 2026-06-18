"""Runtime thật: Actor / Evaluator / Reflector đều gọi LLM qua OpenRouter.

Trước đây file này hardcode (mock). Nay 3 hàm dưới gọi LLM thật bằng các
system prompt trong prompts.py và parse kết quả thành schema tương ứng.
Giữ nguyên chữ ký hàm để agents.py không phải thay đổi.
"""
from __future__ import annotations
from .llm import chat, chat_json
from .prompts import ACTOR_SYSTEM, EVALUATOR_SYSTEM, REFLECTOR_SYSTEM
from .schemas import QAExample, JudgeResult, ReflectionEntry
from .utils import normalize_answer

# Suy ra failure_mode khi đáp án sai. LLM trả về một trong các nhãn này
# (xem REFLECTOR_SYSTEM); nếu không khớp sẽ rơi về giá trị mặc định.
VALID_FAILURE_MODES = {
    "entity_drift",
    "incomplete_multi_hop",
    "wrong_final_answer",
    "looping",
    "reflection_overfit",
}
FAILURE_MODE_BY_QID: dict[str, str] = {}  # giữ tương thích import; runtime thật không dùng bảng cứng


def _format_context(example: QAExample) -> str:
    if not example.context:
        return "(no context provided)"
    return "\n\n".join(f"[{c.title}]\n{c.text}" for c in example.context)


def actor_answer(example: QAExample, attempt_id: int, agent_type: str, reflection_memory: list[str]) -> str:
    """Gửi ACTOR_SYSTEM + question + context (+ reflections) → LLM → câu trả lời."""
    parts = [
        f"Question:\n{example.question}",
        f"Context:\n{_format_context(example)}",
    ]
    if reflection_memory:
        lessons = "\n".join(f"- {s}" for s in reflection_memory)
        parts.append(
            "Reflections from previous failed attempts (apply them):\n" + lessons
        )
    parts.append("Now give ONLY the final answer as a short phrase.")
    user = "\n\n".join(parts)
    return chat(ACTOR_SYSTEM, user).strip().strip('"')


def evaluator(example: QAExample, answer: str) -> JudgeResult:
    """Gửi EVALUATOR_SYSTEM + question + gold + predicted → LLM → JudgeResult."""
    # Phím tắt rẻ tiền & chắc chắn: khớp chính xác sau chuẩn hóa thì khỏi gọi LLM.
    if normalize_answer(example.gold_answer) == normalize_answer(answer):
        return JudgeResult(score=1, reason="Final answer matches the gold answer after normalization.")

    user = (
        f"Question:\n{example.question}\n\n"
        f"Gold answer:\n{example.gold_answer}\n\n"
        f"Candidate answer:\n{answer}\n\n"
        f"Context:\n{_format_context(example)}\n\n"
        "Judge the candidate and respond with the required JSON object."
    )
    data = chat_json(EVALUATOR_SYSTEM, user)
    score = int(data.get("score", 0))
    failure_mode = str(data.get("failure_mode", "")).strip()
    if score == 1:
        failure_mode = "none"
    elif failure_mode not in VALID_FAILURE_MODES:
        failure_mode = "wrong_final_answer"
    return JudgeResult(
        score=score,
        reason=str(data.get("reason", "")),
        missing_evidence=list(data.get("missing_evidence", []) or []),
        spurious_claims=list(data.get("spurious_claims", []) or []),
        failure_mode=failure_mode,
    )


def reflector(example: QAExample, attempt_id: int, judge: JudgeResult) -> ReflectionEntry:
    """Gửi REFLECTOR_SYSTEM + question + wrong answer + lý do sai → LLM → ReflectionEntry."""
    user = (
        f"Question:\n{example.question}\n\n"
        f"Failed attempt id: {attempt_id}\n\n"
        f"Evaluator judgement:\n"
        f"- reason: {judge.reason}\n"
        f"- missing_evidence: {judge.missing_evidence}\n"
        f"- spurious_claims: {judge.spurious_claims}\n\n"
        "Analyze the failure and respond with the required JSON object."
    )
    data = chat_json(REFLECTOR_SYSTEM, user)
    return ReflectionEntry(
        attempt_id=int(data.get("attempt_id", attempt_id)),
        failure_reason=str(data.get("failure_reason", judge.reason)),
        lesson=str(data.get("lesson", "")),
        next_strategy=str(data.get("next_strategy", "")),
    )
