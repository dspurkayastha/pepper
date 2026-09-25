"""One shared AsyncAnthropic client. Tests swap it with set_client()."""

import anthropic

_client = None


def get_client():
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY (and ANTHROPIC_WEBHOOK_SIGNING_KEY for webhooks) from the environment.
        _client = anthropic.AsyncAnthropic()
    return _client


def set_client(client) -> None:
    global _client
    _client = client
