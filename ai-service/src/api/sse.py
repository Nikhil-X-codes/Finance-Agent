"""Encode named server-sent events."""

import json


def stream_event(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"
