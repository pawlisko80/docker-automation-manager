"""
dam/core/pruner.py

Safely removes unused Docker images and optionally dangling
build artifacts after a successful update cycle.

Pruning rules:
  - Never remove images that are currently in use by any container
  - Only remove images that have no tag (dangling) OR that were
    explicitly replaced by a newer pull in this update cycle
  - Dry-run mode: report what would be removed without removing
  - Never remove volumes (data safety)
  - Never remove named networks

Prune targets:
  1. Dangling images  (no tag, no container reference) — always safe
  2. Replaced images  (old digest of a container we just updated)
  3. Unreferenced images (no container uses them) — opt-in only
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import docker
from docker.errors import DockerException, ImageNotFound

from dam.core.updater import UpdateResult, UpdateStatus


# ------------------------------------------------------------
# Result types
# ------------------------------------------------------------

@dataclass
class PruneResult:
    images_removed: list[str]       # image IDs removed
    space_reclaimed_bytes: int       # bytes freed
    errors: list[str]                # any errors during removal
    dry_run: bool                    # whether this was a dry run

    @property
    def space_reclaimed_mb(self) -> float:
        return self.space_reclaimed_bytes / (1024 * 1024)

    @property
    def space_reclaimed_human(self) -> str:
        mb = self.space_reclaimed_bytes / (1024 * 1024)
        if mb >= 1024:
            return f"{mb / 1024:.1f} GB"
        return f"{mb:.1f} MB"


# ------------------------------------------------------------
# Pruner
# ------------------------------------------------------------

class Pruner:
    """
    Removes unused Docker images after an update cycle.
    """

    def __init__(
        self,
        dry_run: bool = False,
        remove_unreferenced: bool = False,
    ):
        """
        Args:
            dry_run:               Report what would be removed, don't remove
            remove_unreferenced:   Also remove images with no running containers
                                   (equivalent to `docker image prune -a`)
        """
        self.dry_run = dry_run
        self.remove_unreferenced = remove_unreferenced

        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException as e:
            raise RuntimeError(f"Cannot connect to Docker daemon: {e}")

    # ------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------

    def prune(
        self,
        update_results: Optional[list[UpdateResult]] = None,
    ) -> PruneResult:
        """
        Run pruning. If update_results provided, also removes the
        old images from containers that were successfully updated.

        Args:
            update_results: Results from Updater.update_all() — used to
                            identify old image IDs to remove
        """
        to_remove: set[str] = set()
        errors: list[str] = []

        # --- Collect old image IDs from successful updates ---
        if update_results:
            for result in update_results:
                if result.status == UpdateStatus.UPDATED and result.old_image_id:
                    to_remove.add(result.old_image_id)

        # --- Collect dangling images (untagged, unreferenced) ---
        dangling = self._get_dangling_images()
        to_remove.update(dangling)

        # --- Optionally collect all unreferenced images ---
        if self.remove_unreferenced:
            unreferenced = self._get_unreferenced_images()
            to_remove.update(unreferenced)

        # --- Filter: never remove images in active use ---
        in_use = self._get_images_in_use()
        safe_to_remove = to_remove - in_use

        if self.dry_run:
            # Report what would be removed
            space = self._estimate_space(safe_to_remove)
            return PruneResult(
                images_removed=list(safe_to_remove),
                space_reclaimed_bytes=space,
                errors=[],
                dry_run=True,
            )

        # --- Remove ---
        removed: list[str] = []
        space_reclaimed = 0

        for image_id in safe_to_remove:
            size = self._get_image_size(image_id)
            try:
                self.client.images.remove(image_id, force=False, noprune=False)
                removed.append(image_id)
                space_reclaimed += size
            except ImageNotFound:
                pass  # Already gone
            except Exception as e:
                errors.append(f"Could not remove {image_id[:12]}: {e}")

        return PruneResult(
            images_removed=removed,
            space_reclaimed_bytes=space_reclaimed,
            errors=errors,
            dry_run=False,
        )

    def prune_dangling_only(self) -> PruneResult:
        """
        Convenience: remove only dangling images (safest operation).
        Equivalent to `docker image prune` (without -a).
        """
        return self.prune(update_results=None)

    # ------------------------------------------------------------
    # Image classification helpers
    # ------------------------------------------------------------

    def _get_dangling_images(self) -> set[str]:
        """Return IDs of images with no tag and no container reference."""
        try:
            images = self.client.images.list(filters={"dangling": True})
            return {img.id for img in images}
        except Exception:
            return set()

    def _get_unreferenced_images(self) -> set[str]:
        """
        Return IDs of all images not currently used by any container
        (running or stopped). Equivalent to `docker image prune -a`.
        """
        try:
            all_images = {img.id for img in self.client.images.list()}
            in_use = self._get_images_in_use()
            return all_images - in_use
        except Exception:
            return set()

    def _get_images_in_use(self) -> set[str]:
        """Return image IDs currently referenced by any container (all states)."""
        in_use = set()
        try:
            containers = self.client.containers.list(all=True)
            for c in containers:
                img_id = c.attrs.get("Image", "")
                if img_id:
                    in_use.add(img_id)
                # Also add by full image name so we match both ways
                image_name = c.attrs.get("Config", {}).get("Image", "")
                if image_name:
                    try:
                        img = self.client.images.get(image_name)
                        in_use.add(img.id)
                    except Exception:
                        pass
        except Exception:
            pass
        return in_use

    def _get_image_size(self, image_id: str) -> int:
        """Return the size of an image in bytes, or 0 if unknown."""
        try:
            img = self.client.images.get(image_id)
            return img.attrs.get("Size", 0)
        except Exception:
            return 0

    def _estimate_space(self, image_ids: set[str]) -> int:
        """Estimate total bytes that would be freed by removing these images."""
        total = 0
        for image_id in image_ids:
            total += self._get_image_size(image_id)
        return total

    # ------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------

    def list_candidates(
        self,
        update_results: Optional[list[UpdateResult]] = None,
    ) -> dict:
        """
        Return a report of what would be pruned without removing anything.
        Used by TUI to show prune preview.
        """
        dangling = self._get_dangling_images()
        replaced = set()
        if update_results:
            for r in update_results:
                if r.status == UpdateStatus.UPDATED and r.old_image_id:
                    replaced.add(r.old_image_id)

        unreferenced = set()
        if self.remove_unreferenced:
            unreferenced = self._get_unreferenced_images()

        in_use = self._get_images_in_use()
        all_candidates = (dangling | replaced | unreferenced) - in_use

        return {
            "dangling": list(dangling - in_use),
            "replaced": list(replaced - in_use),
            "unreferenced": list(unreferenced - in_use),
            "total_candidates": len(all_candidates),
            "estimated_space_bytes": self._estimate_space(all_candidates),
            "estimated_space_human": PruneResult(
                images_removed=[],
                space_reclaimed_bytes=self._estimate_space(all_candidates),
                errors=[],
                dry_run=True,
            ).space_reclaimed_human,
        }
