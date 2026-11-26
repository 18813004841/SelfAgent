"""Regression checks for code-review rule scope and partial coverage."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workbench/machine-dashboard-server/tools/code-review-agent"))
from code_review.checks import classify_skill_rules, model_skill_rules, run_local_checkers, unity_runtime_findings


class ReviewRulesTest(unittest.TestCase):
    def test_comments_literals_and_hot_paths(self):
        source = '''class Test {
/* GameObject.Find("ignored");
GameObject.Find("also ignored"); */
void Update() {
  var s = "GameObject.Find(ignored)";
  var text = @"first line
  GameObject.Find(ignored)";
  events += OnEvent;
  text += "value";
  var xs = values.Where(x => x > 0);
  var c = GetComponent<Foo>();
}
void AddListener() { events += OnEvent; }
void Find() { GameObject.Find("real"); }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Test.cs").write_text(source, encoding="utf-8")
            findings = run_local_checkers(root, ["Test.cs"])
        self.assertEqual({(f["line"], f["rule"]) for f in findings}, {(9, "hot-path-performance"), (10, "hot-path-performance"), (11, "unity-api-misuse"), (14, "unity-api-misuse")})

    def test_nested_editor_and_unprotected_branches(self):
        source = '''#if UNITY_EDITOR
#if SOME_FLAG
UnityEditor.EditorApplication.Exit(0);
#else
UnityEditor.EditorApplication.Exit(0);
#endif
#else
UnityEditor.EditorApplication.Exit(0);
#endif
#if UNITY_EDITOR || UNITY_ANDROID
UnityEditor.EditorApplication.Exit(0);
#endif
var text = "UnityEditor.EditorApplication";
'''
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Test.cs").write_text(source, encoding="utf-8")
            findings = unity_runtime_findings(root, ["Test.cs"], ["UnityEditor"])
        self.assertEqual([f["line"] for f in findings], [8, 11])

    def test_partial_local_coverage_keeps_full_clause_for_model(self):
        rules = [{"path": "SKILL.md", "content": "# Performance\nAvoid LINQ and expensive network calls."}]
        coverage = classify_skill_rules(rules)
        self.assertEqual(coverage[0]["mode"], "local_and_model")
        self.assertEqual(model_skill_rules(rules, coverage)[0]["content"], rules[0]["content"])


if __name__ == "__main__":
    unittest.main()
