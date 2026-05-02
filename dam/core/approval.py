"""
dam/core/approval.py
Approval queue for container updates that require owner sign-off.
Supports per-container update policies: auto | notify | approve | hold
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Update policy per container
# auto    — always apply automatically (default)
# notify  — apply automatically but notify after
# approve — notify and wait for owner approval before applying
# hold    — never auto-update, always requires manual action
POLICIES = ("auto", "notify", "approve", "hold")


@dataclass
class PendingUpdate:
    container_name: str
    image: str
    old_digest: str
    new_digest: str
    detected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    status: str = "pending"     # pending | approved | rejected | applied | expired
    approved_by: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "container_name": self.container_name,
            "image": self.image,
            "old_digest": self.old_digest,
            "new_digest": self.new_digest,
            "detected_at": self.detected_at,
            "status": self.status,
            "approved_by": self.approved_by,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PendingUpdate":
        return cls(
            container_name=d["container_name"],
            image=d["image"],
            old_digest=d.get("old_digest", ""),
            new_digest=d.get("new_digest", ""),
            detected_at=d.get("detected_at", ""),
            status=d.get("status", "pending"),
            approved_by=d.get("approved_by"),
            note=d.get("note"),
        )


class ApprovalQueue:
    """Persistent queue of pending container updates awaiting approval."""

    def __init__(self, queue_file: Path):
        self.queue_file = queue_file
        self._items: list[PendingUpdate] = []
        self._load()

    def _load(self) -> None:
        if self.queue_file.exists():
            try:
                data = json.loads(self.queue_file.read_text())
                self._items = [PendingUpdate.from_dict(d) for d in data]
            except Exception:
                self._items = []

    def _save(self) -> None:
        try:
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            self.queue_file.write_text(
                json.dumps([i.to_dict() for i in self._items], indent=2)
            )
        except Exception as e:
            logger.warning("Could not save approval queue: %s", e)

    def add(self, update: PendingUpdate) -> None:
        """Add or update a pending item."""
        # Replace if same container already pending
        self._items = [i for i in self._items
                       if not (i.container_name == update.container_name
                               and i.status == "pending")]
        self._items.append(update)
        self._save()

    def get_pending(self) -> list[PendingUpdate]:
        return [i for i in self._items if i.status == "pending"]

    def get_all(self) -> list[PendingUpdate]:
        return list(self._items)

    def approve(self, container_name: str, note: str = "") -> Optional[PendingUpdate]:
        for item in self._items:
            if item.container_name == container_name and item.status == "pending":
                item.status = "approved"
                item.note = note
                self._save()
                return item
        return None

    def reject(self, container_name: str, note: str = "") -> Optional[PendingUpdate]:
        for item in self._items:
            if item.container_name == container_name and item.status == "pending":
                item.status = "rejected"
                item.note = note
                self._save()
                return item
        return None

    def mark_applied(self, container_name: str) -> None:
        for item in self._items:
            if item.container_name == container_name and item.status in ("approved", "pending"):
                item.status = "applied"
        self._save()

    def clear_applied(self) -> int:
        """Remove applied/rejected items, return count removed."""
        before = len(self._items)
        self._items = [i for i in self._items
                       if i.status not in ("applied", "rejected")]
        self._save()
        return before - len(self._items)


def get_container_policy(settings: dict, container_name: str) -> str:
    """Return update policy for a container. Default is 'auto'."""
    containers = settings.get("containers", {}) or {}
    cfg = containers.get(container_name, {})
    policy = cfg.get("update_policy", "auto")
    return policy if policy in POLICIES else "auto"


def get_maintenance_window(settings: dict) -> Optional[dict]:
    """Return maintenance window config or None if not set."""
    return settings.get("dam", {}).get("maintenance_window")


def in_maintenance_window(settings: dict) -> bool:
    """Return True if current time is within the maintenance window."""
    window = get_maintenance_window(settings)
    if not window or not window.get("enabled"):
        return True  # No window = always allowed
    try:
        from datetime import datetime
        now = datetime.now()
        weekdays = window.get("weekdays", list(range(7)))  # 0=Mon 6=Sun
        if now.weekday() not in weekdays:
            return False
        start_h, start_m = map(int, window.get("start", "02:00").split(":"))
        end_h, end_m = map(int, window.get("end", "04:00").split(":"))
        start_mins = start_h * 60 + start_m
        end_mins = end_h * 60 + end_m
        now_mins = now.hour * 60 + now.minute
        if start_mins <= end_mins:
            return start_mins <= now_mins <= end_mins
        else:
            # Crosses midnight
            return now_mins >= start_mins or now_mins <= end_mins
    except Exception:
        return True
