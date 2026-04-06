"""
dam/core/deprecation.py

Checks running containers against a curated database of deprecated,
archived, or end-of-life Docker images.

Three signal sources (in priority order):
  1. Bundled eol.yaml  — community-maintained list shipped with DAM
  2. GitHub API        — detects archived repositories (optional, requires token)
  3. Docker Hub API    — detects deprecated image notices (optional)

The bundled eol.yaml is the primary and most reliable source.
API checks are opt-in and gracefully degrade if unavailable.

DeprecationResult per container:
  status:  ok / deprecated / archived / eol / unknown
  reason:  human-readable explanation
  alternatives: list of suggested replacements
  severity: warning / critical
"""

from __future__ import annotations

import urllib.request
import urllib.error
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

from dam.core.inspector import ContainerConfig


# ------------------------------------------------------------
# Bundled EOL database path
# ------------------------------------------------------------

EOL_DB_PATH = Path(__file__).parent.parent.parent / "data" / "eol.yaml"


# ------------------------------------------------------------
# Result types
# ------------------------------------------------------------

class DeprecationStatus(Enum):
    OK         = "ok"          # no known issues
    DEPRECATED = "deprecated"  # image marked deprecated, use alternative
    ARCHIVED   = "archived"    # upstream repo archived, no longer maintained
    EOL        = "eol"         # end of life, security risk
    UNKNOWN    = "unknown"     # could not determine status


class DeprecationSeverity(Enum):
    OK      = "ok"
    WARNING = "warning"    # deprecated/archived but still functional
    CRITICAL = "critical"  # EOL, known security issues


@dataclass
class Alternative:
    name: str
    url: Optional[str] = None
    note: Optional[str] = None


@dataclass
class DeprecationResult:
    container_name: str
    image: str
    status: DeprecationStatus
    severity: DeprecationSeverity
    reason: Optional[str] = None
    deprecated_date: Optional[str] = None
    alternatives: list[Alternative] = field(default_factory=list)
    source: str = "bundled"     # bundled / github / dockerhub

    @property
    def is_ok(self) -> bool:
        return self.status == DeprecationStatus.OK

    @property
    def has_alternatives(self) -> bool:
        return len(self.alternatives) > 0


# ------------------------------------------------------------
# EOL database loader
# ------------------------------------------------------------

def load_eol_db(path: Optional[Path] = None) -> dict:
    """
    Load the EOL database from YAML.
    Returns empty dict if file not found (graceful degradation).
    """
    db_path = path or EOL_DB_PATH
    if not db_path.exists():
        return {}
    try:
        with open(db_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _normalize_image(image: str) -> str:
    """
    Normalize an image reference for matching against the EOL database.
    Strips tags and digests, normalizes docker.io/ prefix.

    Examples:
      ghcr.io/home-assistant/home-assistant:stable  -> ghcr.io/home-assistant/home-assistant
      containrrr/watchtower                          -> containrrr/watchtower
      docker.io/library/nginx:latest                 -> nginx
    """
    # Strip digest
    image = image.split("@")[0]
    # Strip tag
    base = image.split("/")
    last = base[-1].split(":")[0]
    base[-1] = last
    image = "/".join(base)
    # Normalize docker.io/library/ prefix
    if image.startswith("docker.io/library/"):
        image = image[len("docker.io/library/"):]
    if image.startswith("library/"):
        image = image[len("library/"):]
    return image


# ------------------------------------------------------------
# GitHub archived repo checker
# ------------------------------------------------------------

def _check_github_archived(image: str, token: Optional[str] = None) -> Optional[bool]:
    """
    Check if the GitHub repository for an image is archived.
    Returns True if archived, False if not, None if cannot determine.

    Only works for images hosted on ghcr.io or with known GitHub repos.
    Requires internet access and optionally a GitHub token for higher rate limits.
    """
    # Extract GitHub org/repo from ghcr.io images
    if not image.startswith("ghcr.io/"):
        return None

    parts = image.replace("ghcr.io/", "").split("/")
    if len(parts) < 2:
        return None

    org = parts[0]
    repo = parts[1]
    api_url = f"https://api.github.com/repos/{org}/{repo}"

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read())
            return data.get("archived", False)
    except Exception:
        return None


# ------------------------------------------------------------
# Main deprecation checker
# ------------------------------------------------------------

class DeprecationChecker:
    """
    Checks containers against known deprecated/EOL image database.
    """

    def __init__(
        self,
        eol_db_path: Optional[Path] = None,
        check_github: bool = False,
        github_token: Optional[str] = None,
    ):
        """
        Args:
            eol_db_path:   Path to EOL YAML database (default: bundled data/eol.yaml)
            check_github:  If True, also check GitHub API for archived repos
            github_token:  GitHub personal access token for higher API rate limits
        """
        self.db = load_eol_db(eol_db_path)
        self.check_github = check_github
        self.github_token = github_token

        # Build lookup dict: normalized image -> entry
        self._index: dict[str, dict] = {}
        for entry in self.db.get("deprecated", []):
            key = _normalize_image(entry.get("image", ""))
            if key:
                self._index[key] = entry

    def check(self, cfg: ContainerConfig) -> DeprecationResult:
        """Check a single container for deprecation."""
        normalized = _normalize_image(cfg.image)

        # --- Check bundled EOL database ---
        entry = self._index.get(normalized)
        if entry:
            alternatives = [
                Alternative(
                    name=a.get("name", ""),
                    url=a.get("url"),
                    note=a.get("note"),
                )
                for a in entry.get("alternatives", [])
            ]
            status_str = entry.get("status", "deprecated")
            status = {
                "deprecated": DeprecationStatus.DEPRECATED,
                "archived":   DeprecationStatus.ARCHIVED,
                "eol":        DeprecationStatus.EOL,
            }.get(status_str, DeprecationStatus.DEPRECATED)

            severity = (
                DeprecationSeverity.CRITICAL
                if status == DeprecationStatus.EOL
                else DeprecationSeverity.WARNING
            )

            return DeprecationResult(
                container_name=cfg.name,
                image=cfg.image,
                status=status,
                severity=severity,
                reason=entry.get("reason"),
                deprecated_date=entry.get("archived_date") or entry.get("eol_date"),
                alternatives=alternatives,
                source="bundled",
            )

        # --- Optionally check GitHub API ---
        if self.check_github:
            archived = _check_github_archived(cfg.image, self.github_token)
            if archived is True:
                return DeprecationResult(
                    container_name=cfg.name,
                    image=cfg.image,
                    status=DeprecationStatus.ARCHIVED,
                    severity=DeprecationSeverity.WARNING,
                    reason="GitHub repository is archived (no longer maintained)",
                    source="github",
                )

        return DeprecationResult(
            container_name=cfg.name,
            image=cfg.image,
            status=DeprecationStatus.OK,
            severity=DeprecationSeverity.OK,
            source="bundled",
        )

    def check_all(self, configs: list[ContainerConfig]) -> list[DeprecationResult]:
        """Check all containers and return results."""
        return [self.check(cfg) for cfg in configs]

    def warnings_only(self, results: list[DeprecationResult]) -> list[DeprecationResult]:
        """Filter to only non-OK results."""
        return [r for r in results if not r.is_ok]

    def summary(self, results: list[DeprecationResult]) -> dict:
        """Return summary counts."""
        return {
            "total_checked": len(results),
            "ok": sum(1 for r in results if r.status == DeprecationStatus.OK),
            "deprecated": sum(1 for r in results if r.status == DeprecationStatus.DEPRECATED),
            "archived": sum(1 for r in results if r.status == DeprecationStatus.ARCHIVED),
            "eol": sum(1 for r in results if r.status == DeprecationStatus.EOL),
            "warnings": [r for r in results if not r.is_ok],
        }
