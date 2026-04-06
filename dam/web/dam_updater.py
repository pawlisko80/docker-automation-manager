"""
dam/web/dam_updater.py

Self-update logic for Docker Automation Manager.

Strategy:
  1. Check GitHub releases API for latest version
  2. Compare against running __version__
  3. If update available:
     a. Try git pull (if .git directory exists)
     b. Fall back to: download release zip → extract → replace files

Designed to work inside the QNAP Docker container setup where DAM
source is mounted at /app from /share/Container/docker-automation-manager.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dam import __version__

GITHUB_OWNER = "pawlisko80"
GITHUB_REPO  = "docker-automation-manager"
GITHUB_API   = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_ZIP   = "https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip"

# Root of the DAM installation (where setup.py lives)
DAM_ROOT = Path(__file__).parent.parent.parent


# ------------------------------------------------------------
# Version info
# ------------------------------------------------------------

@dataclass
class VersionInfo:
    current: str
    latest: Optional[str]
    update_available: bool
    release_url: Optional[str]
    release_notes: Optional[str]
    error: Optional[str] = None


def check_latest_version(timeout: int = 5) -> VersionInfo:
    """
    Query GitHub releases API for the latest DAM version.
    Returns VersionInfo with comparison result.
    Gracefully returns error state if network unavailable.
    """
    try:
        req = urllib.request.Request(
            GITHUB_API,
            headers={"Accept": "application/vnd.github.v3+json",
                     "User-Agent": f"dam/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())

        latest_tag = data.get("tag_name", "").lstrip("v")
        release_url = data.get("html_url")
        release_notes = data.get("body", "")[:500]  # first 500 chars

        update_available = _version_gt(latest_tag, __version__)

        return VersionInfo(
            current=__version__,
            latest=latest_tag,
            update_available=update_available,
            release_url=release_url,
            release_notes=release_notes,
        )

    except urllib.error.URLError as e:
        return VersionInfo(
            current=__version__,
            latest=None,
            update_available=False,
            release_url=None,
            release_notes=None,
            error=f"Network error: {e.reason}",
        )
    except Exception as e:
        return VersionInfo(
            current=__version__,
            latest=None,
            update_available=False,
            release_url=None,
            release_notes=None,
            error=str(e),
        )


def _version_gt(a: str, b: str) -> bool:
    """Return True if version a > version b (simple semver comparison)."""
    try:
        def parts(v):
            return tuple(int(x) for x in v.split(".")[:3])
        return parts(a) > parts(b)
    except Exception:
        return False


# ------------------------------------------------------------
# Update execution
# ------------------------------------------------------------

@dataclass
class UpdateResult:
    success: bool
    method: str          # "git" | "zip" | "none"
    new_version: Optional[str]
    message: str
    restart_required: bool = True


def perform_update(target_version: Optional[str] = None) -> UpdateResult:
    """
    Attempt to update DAM to the latest (or specified) version.
    Tries git pull first, falls back to zip download.

    Args:
        target_version: specific version tag to install (e.g. "0.4.0").
                        If None, installs latest.

    Returns:
        UpdateResult with success status and method used.
    """
    # Try git first
    git_result = _try_git_pull()
    if git_result.success:
        return git_result

    # Fall back to zip download
    return _try_zip_update(target_version)


def _try_git_pull() -> UpdateResult:
    """Attempt git pull in DAM_ROOT. Returns result."""
    git_dir = DAM_ROOT / ".git"
    if not git_dir.exists():
        return UpdateResult(
            success=False,
            method="git",
            new_version=None,
            message="No .git directory — not a git checkout",
        )

    try:
        result = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=str(DAM_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            # Re-read version after pull
            new_version = _read_version_after_update()
            return UpdateResult(
                success=True,
                method="git",
                new_version=new_version,
                message=result.stdout.strip() or "Already up to date.",
                restart_required=True,
            )
        else:
            return UpdateResult(
                success=False,
                method="git",
                new_version=None,
                message=f"git pull failed: {result.stderr.strip()}",
            )
    except FileNotFoundError:
        return UpdateResult(
            success=False,
            method="git",
            new_version=None,
            message="git command not found on this system",
        )
    except subprocess.TimeoutExpired:
        return UpdateResult(
            success=False,
            method="git",
            new_version=None,
            message="git pull timed out",
        )
    except Exception as e:
        return UpdateResult(
            success=False,
            method="git",
            new_version=None,
            message=str(e),
        )


def _try_zip_update(target_version: Optional[str] = None) -> UpdateResult:
    """Download release zip from GitHub and replace DAM source files."""
    try:
        # Determine target version
        if not target_version:
            info = check_latest_version()
            if info.error or not info.latest:
                return UpdateResult(
                    success=False,
                    method="zip",
                    new_version=None,
                    message=f"Could not determine latest version: {info.error}",
                )
            target_version = info.latest

        tag = f"v{target_version}"
        zip_url = GITHUB_ZIP.format(
            owner=GITHUB_OWNER,
            repo=GITHUB_REPO,
            tag=tag,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Download zip
            zip_path = tmp_path / "dam_update.zip"
            req = urllib.request.Request(
                zip_url,
                headers={"User-Agent": f"dam/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(zip_path, "wb") as f:
                    shutil.copyfileobj(resp, f)

            # Extract
            extract_dir = tmp_path / "extracted"
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            # Find the extracted root (GitHub zips have a single top-level dir)
            extracted_roots = list(extract_dir.iterdir())
            if not extracted_roots:
                return UpdateResult(
                    success=False, method="zip", new_version=None,
                    message="Empty zip archive",
                )
            src_root = extracted_roots[0]

            # Copy dam/ package and data/ directory
            for subdir in ["dam", "data"]:
                src = src_root / subdir
                dst = DAM_ROOT / subdir
                if src.exists():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)

            # Copy key root files
            for fname in ["requirements.txt", "setup.py", "CHANGELOG.md"]:
                src_file = src_root / fname
                if src_file.exists():
                    shutil.copy2(src_file, DAM_ROOT / fname)

        new_version = _read_version_after_update()
        return UpdateResult(
            success=True,
            method="zip",
            new_version=new_version or target_version,
            message=f"Updated to v{target_version} via zip download",
            restart_required=True,
        )

    except urllib.error.HTTPError as e:
        return UpdateResult(
            success=False, method="zip", new_version=None,
            message=f"HTTP {e.code}: release v{target_version} not found on GitHub",
        )
    except Exception as e:
        return UpdateResult(
            success=False, method="zip", new_version=None,
            message=str(e),
        )


def _read_version_after_update() -> Optional[str]:
    """Re-read __version__ from dam/__init__.py after an update."""
    try:
        init_path = DAM_ROOT / "dam" / "__init__.py"
        content = init_path.read_text()
        for line in content.splitlines():
            if "__version__" in line and "=" in line:
                return line.split("=")[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None
