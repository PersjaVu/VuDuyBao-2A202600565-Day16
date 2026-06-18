"""Chuyển dataset HotpotQA (dev distractor) sang format QAExample của lab.

HotpotQA mỗi mẫu có dạng:
    {
      "_id": "...", "question": "...", "answer": "...",
      "type": "...", "level": "easy|medium|hard",
      "supporting_facts": [[title, sent_id], ...],
      "context": [[title, [sent0, sent1, ...]], ...]   # 10 đoạn (có distractor)
    }

Đầu ra QAExample:
    {
      "qid": "...", "difficulty": "...", "question": "...",
      "gold_answer": "...",
      "context": [{"title": "...", "text": "..."}, ...]
    }

Cách dùng:
    python make_test_set.py --src data/hotpot_dev_distractor_v1.json \
        --out data/my_test_set.json --count 60
"""
from __future__ import annotations
import json
from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

VALID_DIFFICULTY = {"easy", "medium", "hard"}


def convert_one(item: dict, index: int) -> dict:
    difficulty = item.get("level", "hard")
    if difficulty not in VALID_DIFFICULTY:
        difficulty = "hard"
    context = [
        {"title": title, "text": " ".join(sentences).strip()}
        for title, sentences in item.get("context", [])
    ]
    return {
        "qid": item.get("_id") or f"hq{index}",
        "difficulty": difficulty,
        "question": item["question"],
        "gold_answer": item["answer"],
        "context": context,
    }


@app.command()
def main(
    src: str = "data/hotpot_dev_distractor_v1.json",
    out: str = "data/my_test_set.json",
    count: int = 60,
) -> None:
    raw = json.loads(Path(src).read_text(encoding="utf-8"))
    subset = raw[:count]
    converted = [convert_one(item, i) for i, item in enumerate(subset)]
    Path(out).write_text(json.dumps(converted, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(converted)} examples -> {out}")
    print(f"-> benchmark will produce {2 * len(converted)} records (react + reflexion).")


if __name__ == "__main__":
    app()
