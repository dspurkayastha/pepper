import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from pepper import anthropic_client, db
from pepper.agent import runtime
from pepper.config import get_settings


def ev(type_: str, id_: str, **fields):
    return SimpleNamespace(type=type_, id=id_, **fields)


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


class FakeStream:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


class AsyncList:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        self._it = iter(self._items)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeAnthropic:
    """Just enough of AsyncAnthropic for the backend.

    `responder(session_id, events)` returns the events the agent emits after a
    send; they reach an open stream only, like the real SSE stream.
    """

    def __init__(self):
        self.log: list[tuple] = []
        self.streams: dict[str, FakeStream] = {}
        self.history: dict[str, list] = {}
        self.responder = lambda session_id, events: []
        self.message_reply = None  # (stop_reason, text)
        self.session_meta: dict[str, dict] = {}
        self._n = 0

        fake = self

        class Events:
            async def stream(self, session_id):
                fake.log.append(("stream", session_id))
                stream = FakeStream()
                fake.streams[session_id] = stream
                return stream

            async def send(self, session_id, events):
                fake.log.append(("send", session_id, events))
                stream = fake.streams.get(session_id)
                for out in fake.responder(session_id, events):
                    fake.history.setdefault(session_id, []).append(out)
                    if stream is not None:
                        stream.queue.put_nowait(out)

            def list(self, session_id, order="asc"):
                fake.log.append(("list", session_id))
                return AsyncList(fake.history.get(session_id, []))

        class Sessions:
            events = Events()

            async def create(self, **kwargs):
                fake._n += 1
                fake.log.append(("create_session", kwargs))
                return SimpleNamespace(id=f"sesn_{fake._n}")

            async def retrieve(self, session_id):
                meta = fake.session_meta.get(session_id, {})
                return SimpleNamespace(id=session_id, title=meta.get("title"), metadata=meta.get("metadata", {}))

            async def archive(self, session_id):
                fake.log.append(("archive", session_id))

        class Messages:
            async def create(self, **kwargs):
                fake.log.append(("messages.create", kwargs))
                stop_reason, text = fake.message_reply
                content = [text_block(text)] if text is not None else []
                return SimpleNamespace(stop_reason=stop_reason, content=content)

        class Credentials:
            async def create(self, vault_id, **kwargs):
                fake.log.append(("credential.create", vault_id, kwargs))
                return SimpleNamespace(id="vcrd_1")

            async def archive(self, credential_id, vault_id):
                fake.log.append(("credential.archive", credential_id, vault_id))

        class Webhooks:
            def unwrap(self, payload, headers):
                if headers.get("webhook-signature") != "valid":
                    raise ValueError("bad signature")
                body = json.loads(payload)
                return SimpleNamespace(id=body["id"], data=SimpleNamespace(**body["data"]))

        self.beta = SimpleNamespace(
            sessions=Sessions(), messages=Messages(),
            vaults=SimpleNamespace(credentials=Credentials()), webhooks=Webhooks(),
        )

    def end_streams(self):
        for stream in self.streams.values():
            stream.queue.put_nowait(None)


@pytest.fixture
async def fake(tmp_path, monkeypatch):
    ids = tmp_path / "agent_ids.json"
    ids.write_text(json.dumps({"agent_id": "agent_1", "environment_id": "env_1", "vault_id": "vlt_1"}))
    monkeypatch.setenv("PEPPER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PEPPER_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("PEPPER_AGENT_IDS", str(ids))
    monkeypatch.setenv("PEPPER_APP_TOKEN", "bootstrap-secret")
    for name in ("APNS_KEY_PATH", "APNS_KEY_ID", "APNS_TEAM_ID", "PEPPER_SESSION_BUDGET_USD_CENTS"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    db.configure(get_settings().database_url)
    await db.create_all()
    client = FakeAnthropic()
    anthropic_client.set_client(client)
    runtime.pump._tasks.clear()
    yield client
    client.end_streams()
    await db.dispose()
    anthropic_client.set_client(None)
    get_settings.cache_clear()


@pytest.fixture
async def api(fake):
    from pepper.main import create_app

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        enrol = await client.post(
            "/v1/devices/enroll", json={"name": "Dev's iPhone"}, headers={"Authorization": "Bearer bootstrap-secret"},
        )
        assert enrol.status_code == 201, enrol.text
        client.headers["Authorization"] = f"Bearer {enrol.json()['token']}"
        yield client
