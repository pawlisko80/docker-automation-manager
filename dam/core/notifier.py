"""
dam/core/notifier.py
Lightweight notification support: ntfy.sh, generic webhook, and no-op.
Configured via settings.yaml under dam.notifications.
"""
from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    enabled: bool = False
    provider: str = "ntfy"          # ntfy | webhook
    ntfy_url: str = "https://ntfy.sh/dam-updates"
    webhook_url: str = ""
    webhook_headers: dict = field(default_factory=dict)
    on_update: bool = True          # notify when containers updated
    on_failure: bool = True         # notify on update failure
    on_eol: bool = True             # notify when EOL images found

    @classmethod
    def from_settings(cls, settings: dict) -> "NotificationConfig":
        cfg = settings.get("dam", {}).get("notifications", {})
        if not cfg:
            return cls()
        return cls(
            enabled=cfg.get("enabled", False),
            provider=cfg.get("provider", "ntfy"),
            ntfy_url=cfg.get("ntfy_url", "https://ntfy.sh/dam-updates"),
            webhook_url=cfg.get("webhook_url", ""),
            webhook_headers=cfg.get("webhook_headers", {}),
            on_update=cfg.get("on_update", True),
            on_failure=cfg.get("on_failure", True),
            on_eol=cfg.get("on_eol", True),
        )


class Notifier:
    """Send notifications via configured provider."""

    def __init__(self, cfg: NotificationConfig):
        self.cfg = cfg

    def send(self, title: str, message: str, priority: str = "default",
             tags: Optional[list] = None) -> bool:
        """Send a notification. Returns True on success."""
        if not self.cfg.enabled:
            return True
        try:
            if self.cfg.provider == "ntfy":
                return self._send_ntfy(title, message, priority, tags or [])
            elif self.cfg.provider == "webhook":
                return self._send_webhook(title, message)
            else:
                logger.warning("Unknown notification provider: %s", self.cfg.provider)
                return False
        except Exception as e:
            logger.warning("Notification failed: %s", e)
            return False

    def _send_ntfy(self, title: str, message: str,
                   priority: str, tags: list) -> bool:
        url = self.cfg.ntfy_url
        headers = {
            "Title": title,
            "Priority": priority,
            "Content-Type": "text/plain",
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        req = urllib.request.Request(
            url, data=message.encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400

    def _send_webhook(self, title: str, message: str) -> bool:
        if not self.cfg.webhook_url:
            return False
        payload = json.dumps({"title": title, "message": message,
                              "source": "DAM"}).encode()
        headers = {"Content-Type": "application/json",
                   **self.cfg.webhook_headers}
        req = urllib.request.Request(
            self.cfg.webhook_url, data=payload, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 400

    def notify_update_complete(self, updated: int, failed: int,
                               results: list) -> None:
        """Send notification after an update run."""
        if updated == 0 and failed == 0:
            return
        if failed > 0 and self.cfg.on_failure:
            names = [r.container_name for r in results
                     if r.status.value == "failed"]
            self.send(
                title="DAM: Update failures",
                message=f"{failed} container(s) failed: {', '.join(names)}",
                priority="high",
                tags=["warning", "docker"],
            )
        if updated > 0 and self.cfg.on_update:
            names = [r.container_name for r in results
                     if r.status.value == "updated"]
            self.send(
                title=f"DAM: {updated} container(s) updated",
                message="\n".join(names),
                priority="default",
                tags=["white_check_mark", "docker"],
            )

    def test(self) -> bool:
        """Send a test notification."""
        return self.send(
            title="DAM: Test notification",
            message="Notifications are working correctly.",
            priority="default",
            tags=["test"],
        )
