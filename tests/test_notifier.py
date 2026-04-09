"""Tests for dam.core.notifier."""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dam.core.notifier import Notifier, NotificationConfig


class TestNotificationConfig(unittest.TestCase):

    def test_defaults(self):
        cfg = NotificationConfig()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.provider, "ntfy")
        self.assertTrue(cfg.on_update)

    def test_from_settings_empty(self):
        cfg = NotificationConfig.from_settings({})
        self.assertFalse(cfg.enabled)

    def test_from_settings_ntfy(self):
        settings = {
            "dam": {
                "notifications": {
                    "enabled": True,
                    "provider": "ntfy",
                    "ntfy_url": "https://ntfy.sh/my-topic",
                }
            }
        }
        cfg = NotificationConfig.from_settings(settings)
        self.assertTrue(cfg.enabled)
        self.assertEqual(cfg.ntfy_url, "https://ntfy.sh/my-topic")

    def test_from_settings_webhook(self):
        settings = {
            "dam": {
                "notifications": {
                    "enabled": True,
                    "provider": "webhook",
                    "webhook_url": "https://hooks.example.com/notify",
                }
            }
        }
        cfg = NotificationConfig.from_settings(settings)
        self.assertEqual(cfg.provider, "webhook")
        self.assertEqual(cfg.webhook_url, "https://hooks.example.com/notify")


class TestNotifier(unittest.TestCase):

    def test_disabled_send_returns_true(self):
        cfg = NotificationConfig(enabled=False)
        notifier = Notifier(cfg)
        self.assertTrue(notifier.send("title", "msg"))

    def test_unknown_provider_returns_false(self):
        cfg = NotificationConfig(enabled=True, provider="unknown")
        notifier = Notifier(cfg)
        self.assertFalse(notifier.send("title", "msg"))

    def test_send_ntfy_success(self):
        cfg = NotificationConfig(enabled=True, provider="ntfy",
                                  ntfy_url="https://ntfy.sh/test")
        notifier = Notifier(cfg)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = notifier.send("title", "message")
        self.assertTrue(result)

    def test_send_ntfy_failure(self):
        cfg = NotificationConfig(enabled=True, provider="ntfy",
                                  ntfy_url="https://ntfy.sh/test")
        notifier = Notifier(cfg)
        with patch("urllib.request.urlopen", side_effect=Exception("conn refused")):
            result = notifier.send("title", "message")
        self.assertFalse(result)

    def test_send_webhook_no_url(self):
        cfg = NotificationConfig(enabled=True, provider="webhook", webhook_url="")
        notifier = Notifier(cfg)
        self.assertFalse(notifier.send("title", "msg"))

    def test_notify_update_complete_no_changes(self):
        cfg = NotificationConfig(enabled=True)
        notifier = Notifier(cfg)
        with patch.object(notifier, "send") as mock_send:
            notifier.notify_update_complete(0, 0, [])
            mock_send.assert_not_called()

    def test_notify_update_complete_updated(self):
        cfg = NotificationConfig(enabled=True, on_update=True, on_failure=True)
        notifier = Notifier(cfg)

        class FakeResult:
            def __init__(self, name, status):
                self.container_name = name
                self.status = MagicMock(value=status)

        results = [FakeResult("ha", "updated"), FakeResult("qbt", "skipped")]
        with patch.object(notifier, "send", return_value=True) as mock_send:
            notifier.notify_update_complete(1, 0, results)
            mock_send.assert_called_once()
            args = mock_send.call_args[1] if mock_send.call_args[1] else {}
            call_args = mock_send.call_args
            self.assertIn("updated", call_args[1].get("title", "") or call_args[0][0])

    def test_notify_update_complete_failed(self):
        cfg = NotificationConfig(enabled=True, on_update=True, on_failure=True)
        notifier = Notifier(cfg)

        class FakeResult:
            def __init__(self, name, status):
                self.container_name = name
                self.status = MagicMock(value=status)

        results = [FakeResult("ha", "failed")]
        with patch.object(notifier, "send", return_value=True) as mock_send:
            notifier.notify_update_complete(0, 1, results)
            mock_send.assert_called_once()
            call_args = mock_send.call_args
            title = call_args[1].get("title", "") or call_args[0][0]
            self.assertIn("failure", title.lower())

    def test_test_method(self):
        cfg = NotificationConfig(enabled=True)
        notifier = Notifier(cfg)
        with patch.object(notifier, "send", return_value=True) as mock_send:
            result = notifier.test()
            self.assertTrue(result)
            mock_send.assert_called_once()


if __name__ == "__main__":
    unittest.main()
