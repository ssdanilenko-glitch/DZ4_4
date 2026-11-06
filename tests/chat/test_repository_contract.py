import pytest
from uuid import uuid4
from app.chat.domain import ChatMessage
import asyncio

pytestmark = pytest.mark.asyncio


async def test_create_and_get_chat(repo):
    chat = await repo.create_chat("owner123", "web", "You are helpful")
    assert chat.id is not None
    fetched = await repo.get_chat(chat.id)
    assert fetched is not None
    assert fetched.owner_external_id == "owner123"
    assert fetched.interface == "web"
    assert fetched.system_prompt == "You are helpful"


async def test_append_and_list_messages(repo):
    chat = await repo.create_chat("owner", "cli")
    msg1 = ChatMessage(chat_id=chat.id, role="user", content="Hello")

    msg2 = ChatMessage(chat_id=chat.id, role="assistant", content="Hi")
    await repo.append_message(chat.id, msg1)
    await asyncio.sleep(0.01)
    await repo.append_message(chat.id, msg2)

    msgs = await repo.list_messages(chat.id)
    assert len(msgs) == 2
    assert msgs[0].content == "Hello"  # хронологический порядок
    assert msgs[1].content == "Hi"


async def test_list_messages_limit(repo):
    chat = await repo.create_chat("owner", "cli")
    for i in range(10):
        msg = ChatMessage(chat_id=chat.id, role="user", content=f"msg{i}")
        await repo.append_message(chat.id, msg)

    msgs = await repo.list_messages(chat.id, limit=3)
    assert len(msgs) == 3
    assert msgs[0].content == "msg7"   # последние 3
    assert msgs[1].content == "msg8"
    assert msgs[2].content == "msg9"


async def test_soft_delete_messages(repo):
    chat = await repo.create_chat("owner", "cli")
    for i in range(5):
        msg = ChatMessage(chat_id=chat.id, role="user", content=f"msg{i}")
        await repo.append_message(chat.id, msg)

    # Удаляем историю
    await repo.soft_delete_messages(chat.id)

    msgs = await repo.list_messages(chat.id)
    assert len(msgs) == 0   # пусто

    # Новые сообщения после удаления должны быть видны
    new_msg = ChatMessage(chat_id=chat.id, role="user", content="new")
    await repo.append_message(chat.id, new_msg)
    msgs = await repo.list_messages(chat.id)
    assert len(msgs) == 1
    assert msgs[0].content == "new"


async def test_get_chat_unknown(repo):
    unknown = uuid4()
    chat = await repo.get_chat(unknown)
    assert chat is None


async def test_list_messages_on_empty_chat(repo):
    chat = await repo.create_chat("owner", "cli")
    msgs = await repo.list_messages(chat.id)
    assert msgs == []


async def test_append_message_returns_message(repo):
    chat = await repo.create_chat("owner", "cli")
    msg = ChatMessage(chat_id=chat.id, role="user", content="test")
    returned = await repo.append_message(chat.id, msg)
    assert returned.id == msg.id
    assert returned.content == "test"