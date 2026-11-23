"""Tests for validating explicit Jenkins user selections before dispatch."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core import jenkins_permissions


class UserSelectionTests(unittest.TestCase):
    def setUp(self):
        self.target = {"ip": "10.0.27.95", "scheme": "http", "port": 8080}
        self.body = {"ip": self.target["ip"], "username": "fengbo", "revision": "a" * 64}
        self.targets = patch.object(jenkins_permissions, "_targets", return_value={self.target["ip"]: self.target})
        self.execute = patch.object(jenkins_permissions, "_execute", return_value={"saved": True})
        self.targets.start()
        self.call = self.execute.start()
        self.addCleanup(self.targets.stop)
        self.addCleanup(self.execute.stop)

    def test_matrix_selection_including_empty_is_forwarded(self):
        result = jenkins_permissions.save({**self.body, "strategy": "matrix", "selection": []})
        self.assertTrue(result["saved"])
        self.call.assert_called_once_with(self.target, {"action": "save", "username": "fengbo", "revision": "a" * 64, "permissions": []})

    def test_role_selection_keeps_scopes(self):
        roles = ["globalRoles:qa", "projectRoles:dev"]
        jenkins_permissions.save({**self.body, "strategy": "roles", "selection": roles})
        self.call.assert_called_once_with(self.target, {"action": "save_roles", "username": "fengbo", "revision": "a" * 64, "roles": roles})

    def test_invalid_selection_fails_before_jenkins(self):
        for changes in ({"strategy": "roles", "selection": ["x", "x"]}, {"strategy": "other", "selection": []}, {"strategy": "matrix", "selection": [None]}, {"strategy": "matrix", "selection": [""]}, {"strategy": "matrix", "selection": ["x"] * 501}, {"strategy": "matrix", "selection": [], "revision": "bad"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                jenkins_permissions.save({**self.body, **changes})
        self.call.assert_not_called()

    def test_failure_from_jenkins_is_not_hidden(self):
        self.call.side_effect = RuntimeError("权限配置已变更，请重新搜索")
        with self.assertRaisesRegex(RuntimeError, "已变更"):
            jenkins_permissions.save({**self.body, "strategy": "matrix", "selection": ["hudson.model.Hudson.Read"]})


if __name__ == "__main__":
    unittest.main()
