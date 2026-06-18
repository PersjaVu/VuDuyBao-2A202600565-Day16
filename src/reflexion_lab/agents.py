from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from .llm import reset_usage, get_usage
from .mock_runtime import actor_answer, evaluator, reflector
from .schemas import AttemptTrace, QAExample, ReflectionEntry, RunRecord

@dataclass
class BaseAgent:
    agent_type: Literal["react", "reflexion"]
    max_attempts: int = 1
    def run(self, example: QAExample) -> RunRecord:
        reflection_memory: list[str] = []
        reflections: list[ReflectionEntry] = []
        traces: list[AttemptTrace] = []
        final_answer = ""
        final_score = 0
        final_failure_mode = "wrong_final_answer"
        for attempt_id in range(1, self.max_attempts + 1):
            # Đo token & latency THẬT cho riêng attempt này.
            reset_usage()
            answer = actor_answer(example, attempt_id, self.agent_type, reflection_memory)
            judge = evaluator(example, answer)
            final_answer = answer
            final_score = judge.score
            final_failure_mode = "none" if judge.score == 1 else judge.failure_mode

            # Logic Reflexion: chỉ reflect khi sai, là reflexion agent và còn lượt thử.
            reflection_entry: ReflectionEntry | None = None
            if judge.score == 0 and self.agent_type == "reflexion" and attempt_id < self.max_attempts:
                # 1. Gọi Reflector để phân tích lỗi và đề xuất chiến thuật mới
                reflection_entry = reflector(example, attempt_id, judge)
                reflections.append(reflection_entry)
                # 2. Nạp chiến thuật mới vào bộ nhớ để Actor dùng cho lần sau
                reflection_memory.append(reflection_entry.next_strategy)

            # token/latency thật của attempt = tổng các lời gọi LLM ở trên.
            tokens, latency = get_usage()
            trace = AttemptTrace(attempt_id=attempt_id, answer=answer, score=judge.score, reason=judge.reason, reflection=reflection_entry, token_estimate=tokens, latency_ms=latency)
            traces.append(trace)
            if judge.score == 1:
                break
        total_tokens = sum(t.token_estimate for t in traces)
        total_latency = sum(t.latency_ms for t in traces)
        return RunRecord(qid=example.qid, question=example.question, gold_answer=example.gold_answer, agent_type=self.agent_type, predicted_answer=final_answer, is_correct=bool(final_score), attempts=len(traces), token_estimate=total_tokens, latency_ms=total_latency, failure_mode=final_failure_mode, reflections=reflections, traces=traces)

class ReActAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_type="react", max_attempts=1)

class ReflexionAgent(BaseAgent):
    def __init__(self, max_attempts: int = 3) -> None:
        super().__init__(agent_type="reflexion", max_attempts=max_attempts)
