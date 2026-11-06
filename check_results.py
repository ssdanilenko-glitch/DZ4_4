import json
from pathlib import Path

# Найти последний файл прогона
runs_dir = Path('eval/runs')
if not runs_dir.exists():
    print(f"❌ Папка {runs_dir} не найдена")
    exit(1)

runs = sorted(runs_dir.glob('*.json'))
if not runs:
    print(f"❌ В папке {runs_dir} нет JSON-файлов")
    exit(1)

latest_run = runs[-1]
print(f"📊 Анализируем прогон: {latest_run.name}\n")

with open(latest_run, encoding='utf-8') as f:
    data = json.load(f)

# Агрегаты
print("=== Агрегаты ===")
for k, v in data.get('aggregates', {}).items():
    print(f"  {k}: {v}")
print()

# Кейсы с correctness < 2
print('=== Кейсы с correctness < 2 ===')
found = False
for item in data.get('items', []):
    scores = item.get('scores', {})
    if scores.get('correctness', 5) < 2:
        found = True
        print(f"ID: {item['id']}")
        print(f"Вопрос: {item['question']}")
        expected = item.get('expected', '')
        answer = item.get('answer', '')
        print(f"Ожидалось: {expected[:150]}...")
        print(f"Получено: {answer[:150]}...")
        print(f"Оценка: {scores}")
        print(f"Причина: {item.get('reasoning', 'N/A')}")
        print('---')

if not found:
    print("✅ Нет кейсов с correctness < 2")