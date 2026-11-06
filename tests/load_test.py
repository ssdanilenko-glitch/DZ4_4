#!/usr/bin/env python3
"""
Скрипт для тестирования rate limiting.
Отправляет N запросов в /chat и проверяет, что превышение лимита возвращает 429.
"""

import asyncio
import httpx
import time

URL = "http://localhost:8000/chat"
PAYLOAD = {
    "messages": [{"role": "user", "content": "Hello"}],
    "model": "gpt-4o-mini",
    "temperature": 0
}
LIMIT = 30  # должно совпадать с настройкой в .env

async def send_request(client, request_id):
    try:
        resp = await client.post(URL, json=PAYLOAD)
        return request_id, resp.status_code
    except Exception as e:
        return request_id, str(e)

async def main():
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = []
        for i in range(LIMIT + 1):  # 31 запрос
            tasks.append(send_request(client, i))
        # Отправляем все запросы одновременно (или почти одновременно)
        results = await asyncio.gather(*tasks)

        # Анализ
        statuses = [code for _, code in results]
        count_429 = statuses.count(429)
        count_200 = statuses.count(200)

        print(f"Всего запросов: {len(results)}")
        print(f"Успешных (200): {count_200}")
        print(f"Отклонённых (429): {count_429}")

        if count_429 >= 1:
            print("Тест пройден: rate limiting работает.")
        else:
            print("Тест не пройден: ожидалась хотя бы одна ошибка 429.")

if __name__ == "__main__":
    asyncio.run(main())