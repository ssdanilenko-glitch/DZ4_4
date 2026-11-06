"""
Прогон golden dataset через LLM-as-judge (G-Eval, reason-then-score).

Использование:
    python eval/run_evaluation.py \
        --golden eval/golden_dataset.json \
        --judge gpt-4o \
        --out eval/runs/2026-06-20.json
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import date
from pathlib import Path

# 🔧 КРИТИЧНО: Добавляем корень проекта в sys.path ПЕРЕД всеми импортами из app
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx
from openai import AsyncOpenAI

# Теперь импорт сработает корректно
from app.core.config import get_settings


JUDGE_PROMPT = """Ты — независимый оценщик ответов LLM. 
Оцени ответ по трём критериям от 1 до 5:
- relevance: насколько ответ релевантен вопросу
- correctness: насколько ответ фактически корректен
- completeness: насколько ответ полон

Эталонный ответ:
{expected}

Вопрос пользователя:
{question}

Ответ тестируемой модели:
{actual}

ВАЖНО: сначала напиши reasoning (краткое обоснование), потом — score.
Верни СТРОГО JSON в формате:
{{
  "reasoning": "...",
  "scores": {{
    "relevance": <1-5>,
    "correctness": <1-5>,
    "completeness": <1-5>
  }},
  "explanation": "одна строка с общим выводом"
}}
"""


async def ask_tested_model(client: httpx.AsyncClient, question: str) -> str:
    """Запрос к тестируемому сервису через HTTP."""
    resp = await client.post(
        "http://localhost:8000/chat",
        json={
            "messages": [{"role": "user", "content": question}],
            "temperature": 0,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()["content"]


async def judge_answer(
    judge_client: AsyncOpenAI,
    judge_model: str,
    question: str,
    expected: str,
    actual: str,
) -> dict:
    """G-Eval: judge-модель оценивает ответ."""
    prompt = JUDGE_PROMPT.format(
        question=question, expected=expected, actual=actual
    )
    response = await judge_client.chat.completions.create(
        model=judge_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


async def run(args):
    golden_path = Path(args.golden)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    items = golden["items"]

    # 🔧 Используем настройки из вашего приложения
    settings = get_settings()

    judge_client = AsyncOpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,  # Используем тот же прокси
    )
    http_client = httpx.AsyncClient()

    results = []
    for item in items:
        print(f"[{item['id']}] {item['question'][:60]}...")
        try:
            actual = await ask_tested_model(http_client, item["question"])
            evaluation = await judge_answer(
                judge_client, args.judge,
                item["question"], item["expected_answer"], actual,
            )
            results.append({
                "id": item["id"],
                "question": item["question"],
                "expected": item["expected_answer"],
                "answer": actual,
                "scores": evaluation["scores"],
                "reasoning": evaluation["reasoning"],
                "explanation": evaluation["explanation"],
            })
        except Exception as e:
            print(f"  ⚠ Ошибка: {e}")
            results.append({
                "id": item["id"],
                "question": item["question"],
                "error": str(e),
                "scores": {"relevance": 1, "correctness": 1, "completeness": 1},
            })

    # Агрегаты
    n = len(results)
    aggregates = {
        "relevance_avg": round(sum(r["scores"]["relevance"] for r in results) / n, 2),
        "correctness_avg": round(sum(r["scores"]["correctness"] for r in results) / n, 2),
        "completeness_avg": round(sum(r["scores"]["completeness"] for r in results) / n, 2),
        "min_correctness": min(r["scores"]["correctness"] for r in results),
    }

    artifact = {
        "run_id": f"run-{date.today().isoformat()}",
        "timestamp": date.today().isoformat(),
        "model_under_test": "llm-service",
        "judge_model": args.judge,
        "golden_version": golden.get("version", 1),
        "items": results,
        "aggregates": aggregates,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Артефакт сохранён: {out_path}")
    print(f"📊 Агрегаты: {aggregates}")

    await http_client.aclose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", default="eval/golden_dataset.json")
    parser.add_argument("--judge", default="gpt-4o")
    parser.add_argument("--out", default=f"eval/runs/{date.today().isoformat()}.json")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()