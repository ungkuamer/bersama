"""Discord webhook notifier for sending rich embed status messages.

This module posts embed-styled messages to a Discord channel via webhook.
Network or API errors are logged as warnings rather than raising exceptions.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
from http.client import HTTPSConnection, HTTPResponse
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


class DiscordNotifyError(Exception):
    """Raised when a Discord webhook call fails (caught internally, never
    propagated to callers)."""


class _Connection(Protocol):
    """Protocol for an HTTPS connection so tests can inject mocks."""

    def request(
        self,
        method: str,
        url: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None: ...

    def getresponse(self) -> HTTPResponse: ...

    def close(self) -> None: ...


class DiscordNotifier:
    """Sends rich embed status messages to a Discord channel via webhook.

    Construction requires a full webhook URL.  ``send()`` constructs the
    embed, POSTs it over HTTPS, and swallows network/HTTP errors with a
    warning log.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        _connection_factory: Callable[[str], _Connection] | None = None,
    ) -> None:
        parsed = urllib.parse.urlparse(webhook_url)
        if parsed.scheme != "https":
            raise DiscordNotifyError("Discord webhook URL must use HTTPS.")
        if not parsed.hostname:
            raise DiscordNotifyError("Discord webhook URL is missing a hostname.")
        self._host: str = parsed.hostname
        self._path: str = parsed.path + ("?" + parsed.query if parsed.query else "")
        self._webhook_url: str = webhook_url
        self._connection_factory: Callable[[str], _Connection] = (
            _connection_factory or (lambda host: HTTPSConnection(host))
        )

    def send(
        self,
        *,
        title: str,
        description: str = "",
        color: int | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> None:
        """Post a single embed to the Discord webhook.

        Args:
            title: Embed title (required).
            description: Embed body text.
            color: Decimal colour value (e.g. ``0x00FF00`` for green).
            fields: Optional list of ``{"name", "value", "inline"}`` dicts.
        """
        embed: dict[str, Any] = {"title": title}
        if description:
            embed["description"] = description
        if color is not None:
            embed["color"] = color
        if fields:
            embed["fields"] = fields

        payload = json.dumps({"embeds": [embed]})

        try:
            conn = self._connection_factory(self._host)
            conn.request(
                "POST",
                self._path,
                body=payload,
                headers={"Content-Type": "application/json"},
            )
            response: HTTPResponse = conn.getresponse()
            response.read()  # drain the response
            if response.status not in (200, 204):
                raise DiscordNotifyError(
                    f"Discord webhook returned HTTP {response.status} "
                    f"for {self._webhook_url}"
                )
        except DiscordNotifyError as exc:
            logger.warning("%s", exc)
        except Exception as exc:
            logger.warning(
                "Failed to send Discord webhook to %s: %s",
                self._webhook_url,
                exc,
            )
