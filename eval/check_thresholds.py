"""
Проверяет пороги качества по последнему артефакту прогона.
Завершается с sys.exit(1), если хотя бы один порог нарушен.
"""
import json
import sys
from pathlib import Path

import yaml


THRESHOLDS_PATH = Path("eval/thresholds.yaml")
RUNS_DIR = Path("eval/runs")


def load_latest_run() -> dict:
    runs = sorted(RUNS_DIR.glob("*.json"))
    if not runs:
        print("❌ Нет артефактов прогона в eval/runs/")
        sys.exit(2)
    return json.loads(runs[-1].read_text(encoding="utf-8"))


def load_thresholds() -> dict:
    if not THRESHOLDS_PATH.exists():
        print(f"❌ Файл {THRESHOLDS_PATH} не найден")
        sys.exit(2)
    return yaml.safe_load(THRESHOLDS_PATH.read_text(encoding="utf-8"))


def main():
    run = load_latest_run()
    thresholds = load_thresholds()
    aggregates = run["aggregates"]

    failures = []
    for metric, threshold in thresholds.items():
        actual = aggregates.get(metric)
        if actual is None:
            failures.append(f"  • {metric}: отсутствует в агрегатах")
            continue
        # Для min_* — фактическое значение должно быть >= порога
        # Для *_avg — среднее должно быть >= порога
        if actual < threshold:
            failures.append(f"  • {metric}: {actual} < {threshold}")

    if failures:
        print("❌ Пороги качества НЕ выполнены:")
        for f in failures:
            print(f)
        print(f"\nРелиз заблокирован. Артефакт: {run['run_id']}")
        sys.exit(1)

    print("✅ Все пороги выполнены:")
    for metric, value in aggregates.items():
        print(f"  • {metric}: {value} (порог: {thresholds[metric]})")
    print(f"\nРелиз разрешён. Артефакт: {run['run_id']}")


if __name__ == "__main__":
    main()