# Tóm tắt luồng hoạt động — Reflexion Agent Lab

Tài liệu này tóm tắt cách 4 file chính phối hợp với nhau, và **những chỗ TODO bạn cần hoàn thiện** để chương trình chạy được.

---

## 1. Bức tranh tổng thể

```
run_benchmark.py
   │  load_dataset()  ──> [QAExample, ...]
   │
   ├─> ReActAgent().run(example)        (1 attempt duy nhất)
   └─> ReflexionAgent(max_attempts=3).run(example)   (thử lại + học từ lỗi)
                │
                ▼
        BaseAgent.run()  ── vòng lặp attempt
                │
   ┌────────────┼─────────────┬──────────────┐
   ▼            ▼             ▼              ▼
actor_answer  evaluator   reflector    (gom lại thành)
 (sinh đáp án)(chấm điểm) (rút bài học)   RunRecord
                │
                ▼
        save_jsonl() + build_report() ──> outputs/
```

Điểm khác biệt cốt lõi giữa 2 agent:
- **ReAct**: trả lời 1 lần, sai là chịu (`max_attempts=1`).
- **Reflexion**: nếu sai thì *tự phản tỉnh* (reflect), ghi bài học vào bộ nhớ, rồi thử lại ở attempt sau (`max_attempts=3`).

---

## 2. `schemas.py` — Cấu trúc dữ liệu (CÓ TODO)

Đây là các "khuôn" dữ liệu (Pydantic models) chảy qua toàn hệ thống.

| Model | Vai trò | Trạng thái |
|-------|---------|-----------|
| `QAExample` | 1 câu hỏi + đáp án vàng (gold) + context | ✅ Đã xong |
| `JudgeResult` | Kết quả chấm điểm của Evaluator | ❌ **TODO — đang rỗng** |
| `ReflectionEntry` | 1 bài học rút ra sau khi sai | ❌ **TODO — đang rỗng** |
| `AttemptTrace` | Log 1 lần thử (đáp án, điểm, token, latency) | ✅ Đã xong |
| `RunRecord` | Tổng kết 1 lần chạy 1 câu hỏi | ✅ Đã xong |

> ⚠️ **Đây chính là nguyên nhân lỗi `'JudgeResult' object has no attribute 'score'`**: vì `JudgeResult` đang là `pass` (rỗng), Pydantic bỏ qua mọi field truyền vào.

**Cần điền** (suy ra từ cách dùng trong `mock_runtime.py`):

```python
class JudgeResult(BaseModel):
    score: int                                          # 0 hoặc 1
    reason: str                                         # lý do chấm điểm
    missing_evidence: list[str] = Field(default_factory=list)
    spurious_claims: list[str] = Field(default_factory=list)

class ReflectionEntry(BaseModel):
    attempt_id: int
    failure_reason: str
    lesson: str
    next_strategy: str
```

---

## 3. `mock_runtime.py` — Logic giả lập (cần biết để sau này thay bằng LLM thật)

File này **giả lập** 3 vai trò của hệ thống (Actor / Evaluator / Reflector) bằng logic cứng (hardcode), thay vì gọi LLM thật. Đây là phần bạn sẽ thay thế khi nâng cấp lên dùng API thật.

| Hàm | Mô phỏng cái gì | Cách giả lập |
|-----|-----------------|--------------|
| `actor_answer()` | **Actor** sinh đáp án | Trả về đáp án sai ở lần đầu (`FIRST_ATTEMPT_WRONG`); nếu là Reflexion và đã có reflection thì trả về đáp án đúng |
| `evaluator()` | **Evaluator** chấm điểm | So sánh đáp án với gold qua `normalize_answer`; đúng → `score=1`, sai → `score=0` kèm lý do |
| `reflector()` | **Reflector** rút bài học | Trả về `ReflectionEntry` với chiến thuật mới tuỳ câu hỏi |

Hằng số hỗ trợ:
- `FIRST_ATTEMPT_WRONG`: ánh xạ qid → đáp án sai cố tình (để demo việc thử-lại).
- `FAILURE_MODE_BY_QID`: ánh xạ qid → loại lỗi (entity_drift, incomplete_multi_hop...).

**Ý tưởng mấu chốt của mock**: Reflexion luôn "đúng ở lần 2" để minh hoạ giá trị của reflection — đây là điểm bạn cần thay bằng LLM thật để có hành vi thực tế.

---

## 4. `agents.py` — Vòng lặp chính (CÓ TODO logic)

`BaseAgent.run()` là trái tim của hệ thống. Vòng lặp cho mỗi câu hỏi:

```
for attempt_id in 1..max_attempts:
    1. answer  = actor_answer(...)        # Actor sinh đáp án (có truyền reflection_memory)
    2. judge   = evaluator(...)           # Evaluator chấm điểm
    3. tạo AttemptTrace (đáp án, điểm, token ước lượng, latency ước lượng)
    4. nếu judge.score == 1:  → lưu trace, BREAK (đã đúng)
    5. [TODO Reflexion]: nếu sai và còn lượt → reflect và nạp bài học vào memory
    6. lưu trace
→ tổng hợp thành RunRecord
```

- `ReActAgent`: `max_attempts=1` → không bao giờ tới bước reflect.
- `ReflexionAgent`: `max_attempts=3` → tận dụng bước reflect để cải thiện.

❌ **TODO bạn cần viết** ở [agents.py:31-35](src/reflexion_lab/agents.py#L31-L35):

```python
# Sau khi judge.score == 0 và chưa break:
if self.agent_type == "reflexion" and attempt_id < self.max_attempts:
    entry = reflector(example, attempt_id, judge)      # gọi Reflector
    reflections.append(entry)
    trace.reflection = entry
    reflection_memory.append(entry.next_strategy)       # nạp bài học cho lần sau
```

> Lưu ý: `actor_answer()` chỉ trả đáp án đúng cho Reflexion **khi `reflection_memory` đã có nội dung** — nên nếu không nạp memory ở bước này, agent sẽ mãi sai.

Ngoài ra còn 2 TODO phụ (không gây lỗi, chỉ là placeholder): `token_estimate` và `latency_ms` đang được ước lượng bằng công thức cứng, sau này thay bằng số đo thật từ LLM.

---

## 5. `prompts.py` — System Prompts (TOÀN BỘ là TODO)

Hiện tại 3 prompt đều rỗng. Chúng **chưa được dùng** trong chế độ mock (vì mock hardcode logic), nhưng là phần bạn phải viết để chuyển sang LLM thật:

| Prompt | Hướng dẫn cho ai | Yêu cầu chính |
|--------|------------------|---------------|
| `ACTOR_SYSTEM` | Actor | Biết đọc & dùng `context` để trả lời, hoàn thành đủ các "hop" suy luận |
| `EVALUATOR_SYSTEM` | Evaluator | Chấm 0/1 và **trả về JSON** khớp với `JudgeResult` |
| `REFLECTOR_SYSTEM` | Reflector | Phân tích lỗi, đề xuất `next_strategy` cụ thể |

---

## 6. Checklist để chạy được `run_benchmark.py`

1. ✅ Định nghĩa field cho `JudgeResult` trong `schemas.py` *(sửa lỗi hiện tại)*
2. ✅ Định nghĩa field cho `ReflectionEntry` trong `schemas.py`
3. ✅ Viết logic Reflexion trong `agents.py` (bước reflect + nạp memory)
4. ⬜ Viết 3 system prompt trong `prompts.py` *(cần khi chuyển sang LLM thật)*
5. ⬜ Thay logic mock trong `mock_runtime.py` bằng lời gọi LLM thật *(nâng cao)*

Lệnh chạy:
```bash
python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/sample_run
```
Kết quả: `react_runs.jsonl`, `reflexion_runs.jsonl` và report (JSON + Markdown) trong thư mục `outputs/`.

---

## 7. Đã hoàn thiện những gì (Bước 2) — và vì sao

Dưới đây là chính xác các thay đổi đã thực hiện, để bạn nắm được luồng sau khi hoàn thiện.

### 7.1. `schemas.py` — điền field cho 2 model rỗng

```python
class JudgeResult(BaseModel):
    score: int                                          # 1 = đúng, 0 = sai
    reason: str
    missing_evidence: list[str] = Field(default_factory=list)
    spurious_claims: list[str] = Field(default_factory=list)

class ReflectionEntry(BaseModel):
    attempt_id: int
    failure_reason: str
    lesson: str
    next_strategy: str
```

**Vì sao đúng các field này:** chúng được suy ra trực tiếp từ cách `mock_runtime.py`
khởi tạo object. `evaluator()` truyền `score`, `reason`, `missing_evidence`,
`spurious_claims`; `reflector()` truyền `attempt_id`, `failure_reason`, `lesson`,
`next_strategy`. Hai field list để `default_factory=list` vì có lúc Evaluator không
truyền (trường hợp `score=1`). → Sửa dứt điểm lỗi `'JudgeResult' object has no attribute 'score'`.

### 7.2. `agents.py` (dòng 31-35) — vòng lặp Reflexion

```python
if self.agent_type == "reflexion" and attempt_id < self.max_attempts:
    entry = reflector(example, attempt_id, judge)   # 1. phân tích lỗi
    reflections.append(entry)                        #    lưu vào danh sách reflection
    trace.reflection = entry                         # 2. gắn vào trace của lần thử này
    reflection_memory.append(entry.next_strategy)    # 3. nạp chiến thuật cho lần sau
traces.append(trace)
```

**Luồng sau khi điền — vì sao Reflexion thắng ReAct:**
1. Attempt 1: `actor_answer()` trả đáp án **sai** (theo `FIRST_ATTEMPT_WRONG`) → `judge.score = 0`.
2. Vì là `reflexion` và còn lượt → gọi `reflector()`, lấy `next_strategy` nạp vào `reflection_memory`.
3. Attempt 2: `actor_answer()` thấy `reflection_memory` **đã có nội dung** → trả đáp án **đúng** → `score = 1` → `break`.

> Điều kiện `attempt_id < self.max_attempts` tránh reflect thừa ở lần thử cuối (vì sẽ không còn attempt nào để dùng bài học). ReAct có `max_attempts=1` nên nhánh `if` không bao giờ chạy → nó luôn dừng sau 1 lần.

### 7.3. `prompts.py` — 3 system prompt

- **`ACTOR_SYSTEM`**: buộc Actor chỉ dùng `context`, hoàn thành đủ chuỗi suy luận
  (multi-hop), và **áp dụng các reflection** từ lần trước nếu có. Output chỉ là đáp án ngắn.
- **`EVALUATOR_SYSTEM`**: chấm 0/1 và **bắt buộc trả về JSON** đúng khuôn `JudgeResult`
  (score, reason, missing_evidence, spurious_claims) — để parse trực tiếp thành object.
- **`REFLECTOR_SYSTEM`**: phân tích failure mode (entity_drift / incomplete_multi_hop /
  wrong_final_answer) và **trả JSON** đúng khuôn `ReflectionEntry`, với `next_strategy`
  cụ thể, hành động được.

> Lưu ý: ở chế độ **mock** hiện tại, 3 prompt này **chưa được gọi** (logic do `mock_runtime.py`
> hardcode). Chúng là phần chuẩn bị sẵn cho bước nâng cấp dùng LLM thật — khi đó, prompt được
> thiết kế để output khớp đúng schema nên có thể parse JSON thẳng thành `JudgeResult`/`ReflectionEntry`.

### 7.4. Kết quả kiểm chứng

Chạy `python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/sample_run`:

| Agent | EM (độ chính xác) | Avg attempts | Avg tokens | Avg latency |
|-------|------|--------------|-----------|-------------|
| ReAct | **0.50** | 1.0 | 385 | 200 ms |
| Reflexion | **1.00** | 1.5 | 790 | 455 ms |

→ Reflexion đạt EM cao hơn 0.5 nhờ thử lại sau khi học từ lỗi, **đánh đổi** bằng nhiều
token và latency hơn (vì có thêm lượt reflect + retry). Đây chính là bài học cốt lõi của lab.

> ⚠️ Bảng kết quả trên là từ chế độ **mock**. Sau Bước 3 (LLM thật) con số sẽ khác và
> phụ thuộc vào model bạn chọn.

---

## 8. Bước 3 — Thay Mock bằng LLM thật (OpenRouter)

Toàn bộ pipeline giờ gọi **LLM thật** qua **OpenRouter** (API tương thích chuẩn OpenAI).
Không còn logic hardcode nào quyết định đúng/sai.

### 8.1. Kiến trúc sau khi đổi

```
agents.py
  └─ reset_usage()            # bắt đầu đo token+latency cho 1 attempt
  └─ actor_answer()  ─┐
  └─ evaluator()      ├─> llm.chat()/chat_json() ──> OpenRouter ──> model
  └─ reflector()     ─┘        (cộng dồn token & latency thật)
  └─ get_usage()              # lấy token+latency thật của attempt
```

| File | Vai trò mới |
|------|-------------|
| **`llm.py`** (mới) | Client OpenRouter. `chat()` trả text, `chat_json()` trả dict (tự gỡ ```fence```). Đo **token & latency thật** qua `reset_usage()/get_usage()`. Đọc config từ `.env`. |
| **`mock_runtime.py`** | 3 hàm `actor_answer / evaluator / reflector` giờ build prompt + gọi LLM + parse ra schema. Tên file giữ nguyên để khỏi đụng import. |
| **`agents.py`** | Đo usage thật mỗi attempt; `failure_mode` lấy từ Evaluator (không còn bảng cứng). |
| **`schemas.py`** | `JudgeResult` thêm field `failure_mode`. |
| **`prompts.py`** | `EVALUATOR_SYSTEM` yêu cầu trả thêm `failure_mode`. |

### 8.2. Ba hàm gọi LLM (đúng theo yêu cầu Bước 3)

| Hàm | Gửi đi | Nhận về |
|-----|--------|---------|
| `actor_answer()` | `ACTOR_SYSTEM` + question + context (+ reflections nếu có) | câu trả lời (text) |
| `evaluator()` | `EVALUATOR_SYSTEM` + question + gold + predicted + context | JSON → `JudgeResult` |
| `reflector()` | `REFLECTOR_SYSTEM` + question + attempt sai + lý do sai | JSON → `ReflectionEntry` |

Lưu ý:
- `evaluator()` có **phím tắt**: nếu đáp án khớp gold sau chuẩn hóa thì chấm 1 ngay,
  khỏi tốn 1 lời gọi LLM.
- Actor **không** nhận gold answer (đúng tinh thần: nó phải tự suy luận). Chỉ Evaluator mới thấy gold.
- Token & latency trong report giờ là **số thật** từ API, không phải công thức ước lượng.

### 8.3. Cấu hình (.env)

Đã tạo sẵn `.env` ở thư mục gốc — bạn chỉ cần **dán key** vào:

```ini
OPENROUTER_API_KEY=sk-or-...                      # lấy ở https://openrouter.ai/keys
OPENROUTER_MODEL=openai/gpt-oss-120b:free         # đổi model tùy ý
OPENROUTER_MAX_TOKENS=2000                         # chặn token để tránh lỗi 402
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

> **Vì sao dùng model `:free`?** Account OpenRouter hiện gần hết credit (chỉ "afford"
> ~542 token cho model trả phí → lỗi 402). Model free `llama-3.3-70b` lại bị rate-limit
> 429 nặng (1 call mất 61s vẫn fail). `openai/gpt-oss-120b:free` phản hồi nhanh (~4s),
> ổn định nên được chọn làm mặc định. Muốn dùng Claude/GPT trả phí: nạp credit rồi đổi `OPENROUTER_MODEL`.

### 8.5. Gia cố cho LLM thật (model free hay lỗi vặt)
`llm.py` có sẵn cơ chế chịu lỗi để chạy benchmark dài không bị gãy:
- Retry + backoff khi gặp **429** (tôn trọng `Retry-After`).
- Retry khi response **rỗng** (`choices`/`content` trống — provider lỗi tạm thời).
- `chat_json()` **parse JSON có retry** (model free đôi khi trả JSON hỏng).

`.env` đã nằm trong `.gitignore` nên key không bị commit. Dependency `openai` đã được
thêm vào `requirements.txt` và cài vào `.venv`.

### 8.4. Cách chạy

```bash
# 1) dán OPENROUTER_API_KEY vào .env
# 2) chạy
python run_benchmark.py --dataset data/hotpot_mini.json --out-dir outputs/sample_run
```

Nếu thiếu key sẽ báo lỗi rõ ràng: *"Missing OPENROUTER_API_KEY..."*.

---

## 9. Bước 4 — Tạo dữ liệu test & chạy Benchmark (≥100 records)

### 9.1. Vì sao cần ≥100 records
`autograde.py` chấm điểm phần Experiment dựa trên `meta.num_records >= 100`.
Trong `reporting.py`, `num_records = len(records) = số bản ghi react + reflexion = 2 × số example`.
→ Chỉ cần **≥50 example** là đạt ≥100 records. Mình tạo **60 example** (=120 records, dư an toàn).

### 9.2. Script chuyển đổi: `make_test_set.py`
Chuyển **HotpotQA dev (distractor)** → format `QAExample`:

| HotpotQA | QAExample |
|----------|-----------|
| `_id` | `qid` |
| `level` (easy/medium/hard) | `difficulty` |
| `question` | `question` |
| `answer` | `gold_answer` |
| `context` = `[[title, [sent…]], …]` | `context` = `[{title, text}, …]` (nối các câu) |

Chạy:
```bash
python make_test_set.py --src data/hotpot_dev_distractor_v1.json \
    --out data/my_test_set.json --count 60
```
→ tạo `data/my_test_set.json` (60 câu, mỗi câu 10 đoạn context có cả "distractor").

### 9.3. Chạy benchmark
```bash
python run_benchmark.py --dataset data/my_test_set.json \
    --out-dir outputs/my_test_set --reflexion-attempts 2
```
Kết quả lưu ở `outputs/my_test_set/`: `react_runs.jsonl`, `reflexion_runs.jsonl`,
`report.json`, `report.md`.

> Dùng `--reflexion-attempts 2` để giảm số lời gọi LLM (model free chậm). Kết quả benchmark
> thực tế sẽ được điền vào đây sau khi chạy xong.
