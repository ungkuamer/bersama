"""Tests for DiscordNotifier — embed construction and HTTP behaviour."""

from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from bersama.discord_notifier import DiscordNotifier


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_mock_connection(status: int = 204, body: bytes = b"") -> MagicMock:
    """Create a mock connection that returns the given status and body."""
    mock_conn = MagicMock()
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.read.return_value = body
    mock_conn.getresponse.return_value = mock_response
    return mock_conn


def _capture_request_body(mock_conn: MagicMock) -> dict[str, Any]:
    """Extract the JSON body that was passed to conn.request()."""
    args, kwargs = mock_conn.request.call_args
    body_str = kwargs.get("body", "{}")
    return json.loads(body_str)


def _capture_request_headers(mock_conn: MagicMock) -> dict[str, str] | None:
    """Extract the headers dict passed to conn.request()."""
    _, kwargs = mock_conn.request.call_args
    return kwargs.get("headers")


# ── tests ────────────────────────────────────────────────────────────────────


class TestDiscordNotifierSend:
    """Tests for DiscordNotifier.send() — embed construction and sending."""

    def test_sends_webhook_with_correct_url(self) -> None:
        """HTTP POST is sent to the webhook URL path."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"
        mock_conn = _make_mock_connection()

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=lambda host: mock_conn,
        )
        notifier.send(title="Test Title", description="Test Description")

        mock_conn.request.assert_called_once()
        args, kwargs = mock_conn.request.call_args
        # Method should be POST
        assert args[0] == "POST"
        # Path should match the webhook path
        assert args[1] == "/api/webhooks/12345/token"

    def test_sends_correct_embed_payload(self) -> None:
        """The POST body contains a valid Discord embed structure."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"
        mock_conn = _make_mock_connection()

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=lambda host: mock_conn,
        )
        notifier.send(
            title="Build Status",
            description="PR #42 merged successfully.",
            color=0x00FF00,
            fields=[
                {"name": "Branch", "value": "impl/141/142-discord", "inline": True},
                {"name": "Status", "value": "✅ Passed", "inline": True},
            ],
        )

        body = _capture_request_body(mock_conn)
        assert "embeds" in body
        assert len(body["embeds"]) == 1
        embed = body["embeds"][0]
        assert embed["title"] == "Build Status"
        assert embed["description"] == "PR #42 merged successfully."
        assert embed["color"] == 0x00FF00
        assert len(embed["fields"]) == 2
        assert embed["fields"][0]["name"] == "Branch"
        assert embed["fields"][0]["value"] == "impl/141/142-discord"
        assert embed["fields"][0]["inline"] is True

    def test_minimal_call_with_defaults(self) -> None:
        """Sending with only a title works with sensible defaults."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"
        mock_conn = _make_mock_connection()

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=lambda host: mock_conn,
        )
        notifier.send(title="Minimal Notification")

        body = _capture_request_body(mock_conn)
        embed = body["embeds"][0]
        assert embed["title"] == "Minimal Notification"
        # description should be absent or empty when not provided
        assert embed.get("description", "") == ""

    def test_content_type_header_is_set(self) -> None:
        """The request includes Content-Type: application/json."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"
        mock_conn = _make_mock_connection()

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=lambda host: mock_conn,
        )
        notifier.send(title="Test")

        headers = _capture_request_headers(mock_conn)
        assert headers is not None
        assert headers["Content-Type"] == "application/json"


class TestDiscordNotifierErrors:
    """Tests for graceful error handling — no exceptions, just warnings."""

    def test_network_error_logs_warning_and_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When the HTTP POST fails with a network error, log a warning."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"

        def _failing_factory(host: str) -> MagicMock:
            raise ConnectionError("Network unreachable")

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=_failing_factory,
        )

        with caplog.at_level(logging.WARNING):
            # Should not raise
            notifier.send(title="Test")

        assert len(caplog.records) >= 1
        warning_message = caplog.records[0].message
        assert "Failed to send Discord webhook" in warning_message
        assert webhook_url in warning_message

    def test_non_200_status_logs_warning_and_does_not_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When Discord returns a non-200/204 status, log a warning."""
        webhook_url = "https://discord.com/api/webhooks/12345/token"
        mock_conn = _make_mock_connection(status=429, body=b'{"retry_after": 1000}')

        notifier = DiscordNotifier(
            webhook_url,
            _connection_factory=lambda host: mock_conn,
        )

        with caplog.at_level(logging.WARNING):
            # Should not raise
            notifier.send(title="Test")

        assert len(caplog.records) >= 1
        warning_message = caplog.records[0].message
        assert "HTTP 429" in warning_message
        assert webhook_url in warning_message
