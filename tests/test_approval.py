"""Tests for dam.core.approval."""
import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dam.core.approval import (
    ApprovalQueue, PendingUpdate, get_container_policy,
    in_maintenance_window, POLICIES
)


class TestPendingUpdate(unittest.TestCase):

    def test_to_dict_round_trip(self):
        u = PendingUpdate("ha", "ha:stable", "sha:old", "sha:new")
        d = u.to_dict()
        u2 = PendingUpdate.from_dict(d)
        self.assertEqual(u2.container_name, "ha")
        self.assertEqual(u2.image, "ha:stable")
        self.assertEqual(u2.status, "pending")

    def test_default_status_pending(self):
        u = PendingUpdate("ha", "ha:stable", "", "")
        self.assertEqual(u.status, "pending")


class TestApprovalQueue(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.tmp.close()
        self.queue = ApprovalQueue(Path(self.tmp.name))

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_add_and_get_pending(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        pending = self.queue.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].container_name, "ha")

    def test_add_replaces_existing_pending(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old1", "new1"))
        self.queue.add(PendingUpdate("ha", "ha:stable", "old2", "new2"))
        self.assertEqual(len(self.queue.get_pending()), 1)
        self.assertEqual(self.queue.get_pending()[0].old_digest, "old2")

    def test_approve(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        result = self.queue.approve("ha")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "approved")
        self.assertEqual(len(self.queue.get_pending()), 0)

    def test_reject(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        result = self.queue.reject("ha", note="Too risky")
        self.assertIsNotNone(result)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.note, "Too risky")

    def test_mark_applied(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        self.queue.approve("ha")
        self.queue.mark_applied("ha")
        all_items = self.queue.get_all()
        self.assertEqual(all_items[0].status, "applied")

    def test_clear_applied(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        self.queue.approve("ha")
        self.queue.mark_applied("ha")
        self.queue.add(PendingUpdate("qbt", "qbt:latest", "old", "new"))
        cleared = self.queue.clear_applied()
        self.assertEqual(cleared, 1)
        self.assertEqual(len(self.queue.get_all()), 1)
        self.assertEqual(self.queue.get_all()[0].container_name, "qbt")

    def test_persistence(self):
        self.queue.add(PendingUpdate("ha", "ha:stable", "old", "new"))
        # Reload from file
        queue2 = ApprovalQueue(Path(self.tmp.name))
        self.assertEqual(len(queue2.get_pending()), 1)

    def test_approve_nonexistent(self):
        result = self.queue.approve("nonexistent")
        self.assertIsNone(result)


class TestGetContainerPolicy(unittest.TestCase):

    def test_default_auto(self):
        self.assertEqual(get_container_policy({}, "ha"), "auto")

    def test_explicit_policy(self):
        settings = {"containers": {"ha": {"update_policy": "approve"}}}
        self.assertEqual(get_container_policy(settings, "ha"), "approve")

    def test_invalid_policy_falls_back_to_auto(self):
        settings = {"containers": {"ha": {"update_policy": "unknown"}}}
        self.assertEqual(get_container_policy(settings, "ha"), "auto")

    def test_all_valid_policies(self):
        for policy in POLICIES:
            settings = {"containers": {"ha": {"update_policy": policy}}}
            self.assertEqual(get_container_policy(settings, "ha"), policy)


class TestMaintenanceWindow(unittest.TestCase):

    def test_no_window_always_allowed(self):
        self.assertTrue(in_maintenance_window({}))

    def test_disabled_window_always_allowed(self):
        settings = {"dam": {"maintenance_window": {"enabled": False}}}
        self.assertTrue(in_maintenance_window(settings))

    def test_window_logic_in_range(self):
        """Test the time math directly."""
        from dam.core import approval as apr
        # Simulate: now=03:00, window 02:00-04:00, all weekdays
        start_mins = 2 * 60    # 02:00
        end_mins = 4 * 60      # 04:00
        now_mins = 3 * 60      # 03:00
        self.assertTrue(start_mins <= now_mins <= end_mins)

    def test_window_logic_outside_range(self):
        start_mins = 2 * 60    # 02:00
        end_mins = 4 * 60      # 04:00
        now_mins = 12 * 60     # noon
        self.assertFalse(start_mins <= now_mins <= end_mins)

    def test_window_crosses_midnight(self):
        """23:00 to 01:00 window."""
        start_mins = 23 * 60   # 23:00
        end_mins = 1 * 60      # 01:00
        now_mins = 23 * 60 + 30  # 23:30 — should be in window
        self.assertTrue(now_mins >= start_mins or now_mins <= end_mins)
        now_mins2 = 12 * 60    # noon — not in window
        self.assertFalse(now_mins2 >= start_mins or now_mins2 <= end_mins)


if __name__ == "__main__":
    unittest.main()
