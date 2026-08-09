from unittest.mock import patch

import pytest

from backend.app.infrastructure.live_graph_draft_adapter import (
    GraphDraftError,
    LiveGraphDraftAdapter,
)


class Response:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data


class Client:
    responses = []
    patches = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, *args, **kwargs):
        return self.responses.pop(0)

    def patch(self, *args, **kwargs):
        self.patches.append(kwargs["json"])
        return Response(204)


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("GRAPH_ENABLED", "True")
    monkeypatch.setenv("DRAFTS_ENABLED", "True")
    monkeypatch.setenv("MAIL_SEND_ENABLED", "False")
    value = LiveGraphDraftAdapter()
    monkeypatch.setattr(value, "_headers", lambda: {})
    Client.responses = []
    Client.patches = []
    return value


def graph_draft(body, marker=None):
    properties = [] if marker is None else [{
        "id": LiveGraphDraftAdapter.IDEMPOTENCY_PROPERTY_ID,
        "value": marker,
    }]
    return {
        "id": "draft-1", "isDraft": True, "conversationId": "conv-1",
        "body": {"contentType": "html", "content": body},
        "toRecipients": [{"emailAddress": {"address": "client@tcs.com"}}],
        "ccRecipients": [], "bccRecipients": [],
        "singleValueExtendedProperties": properties,
    }


def test_finalize_prepends_text_and_preserves_outlook_chain(adapter):
    marker = adapter.marker("idemp-1", "hash-1")
    original_chain = "<div id='divRplyFwdMsg'>From: Tarun<br>Original submission body</div>"
    verified = graph_draft("<div>Approved follow-up</div><br><br>" + original_chain, marker)
    Client.responses = [Response(data=graph_draft(original_chain)), Response(data=verified)]

    with patch("backend.app.infrastructure.live_graph_draft_adapter.httpx.Client", Client):
        adapter.finalize_existing(
            "draft-1", "conv-1", "Approved follow-up", ["client@tcs.com"], [], [],
            "hash-1", "idemp-1",
        )

    patched_body = Client.patches[0]["body"]["content"]
    assert patched_body.startswith("<div>Approved follow-up</div>")
    assert original_chain in patched_body


def test_chain_verification_tolerates_graph_whitespace_normalization(adapter):
    marker = adapter.marker("idemp-1", "hash-1")
    returned = graph_draft(
        "<div>Approved follow-up</div><br><br><div>From: Tarun&nbsp;&nbsp; Original\nsubmission body</div>",
        marker,
    )
    Client.responses = [Response(data=returned)]
    with patch("backend.app.infrastructure.live_graph_draft_adapter.httpx.Client", Client):
        adapter.verify_draft(
            "draft-1", "conv-1", "Approved follow-up", ["client@tcs.com"], [], [], marker,
            "From: Tarun Original submission body",
        )


def test_finalize_is_idempotent_when_marker_already_present(adapter):
    marker = adapter.marker("idemp-1", "hash-1")
    combined = "<div>Approved follow-up</div><br><br><div>Original chain</div>"
    Client.responses = [Response(data=graph_draft(combined, marker)), Response(data=graph_draft(combined, marker))]

    with patch("backend.app.infrastructure.live_graph_draft_adapter.httpx.Client", Client):
        adapter.finalize_existing(
            "draft-1", "conv-1", "Approved follow-up", ["client@tcs.com"], [], [],
            "hash-1", "idemp-1",
        )

    assert Client.patches == []


def test_finalize_fails_closed_when_reply_skeleton_has_no_chain(adapter):
    Client.responses = [Response(data=graph_draft(""))]
    with patch("backend.app.infrastructure.live_graph_draft_adapter.httpx.Client", Client):
        with pytest.raises(GraphDraftError, match="original conversation history"):
            adapter.finalize_existing(
                "draft-1", "conv-1", "Approved follow-up", ["client@tcs.com"], [], [],
                "hash-1", "idemp-1",
            )
    assert Client.patches == []
