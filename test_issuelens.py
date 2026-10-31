"""
Unit and Integration Tests for IssueLens MVP.
Verifies URL parsing, keyword ranking, snippet extraction, schema validation, and pipeline execution.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_engine import (
    GemmaEngine,
    IssueAnalysisResult,
    FileEvidenceItem,
    ImplementationStep,
    InvestigationStep,
    TestCaseItem,
    ChecklistItem,
)
from analyzer import (
    extract_keywords,
    score_file_path,
    rank_relevant_files,
    extract_evidence_snippets,
    is_ignored_path,
)
from github_client import (
    GitHubClient,
    InvalidGitHubURLError,
    parse_github_url,
)
from demo_data import (
    get_demo_repo_metadata,
    get_demo_issue_data,
    get_demo_snippets,
    get_demo_analysis,
)
from sample_data import SAMPLE_ISSUES


class TestGitHubClient(unittest.TestCase):
    def test_parse_valid_repo_url(self):
        result = parse_github_url("https://github.com/psf/requests")
        self.assertEqual(result["owner"], "psf")
        self.assertEqual(result["repo"], "requests")
        self.assertFalse(result["is_issue"])

    def test_parse_valid_issue_url(self):
        result = parse_github_url("https://github.com/pallets/flask/issues/5000")
        self.assertEqual(result["owner"], "pallets")
        self.assertEqual(result["repo"], "flask")
        self.assertEqual(result["issue_number"], 5000)
        self.assertTrue(result["is_issue"])

    def test_parse_issue_url_with_git_suffix(self):
        result = parse_github_url("https://github.com/pallets/flask.git/issues/42")
        self.assertEqual(result["owner"], "pallets")
        self.assertEqual(result["repo"], "flask")
        self.assertEqual(result["issue_number"], 42)

    def test_invalid_host(self):
        with self.assertRaises(InvalidGitHubURLError):
            parse_github_url("https://gitlab.com/owner/repo/issues/1")

    def test_empty_url(self):
        with self.assertRaises(InvalidGitHubURLError):
            parse_github_url("")

    def test_incomplete_path(self):
        with self.assertRaises(InvalidGitHubURLError):
            parse_github_url("https://github.com/onlyowner")


class TestAnalyzer(unittest.TestCase):
    def test_keyword_extraction(self):
        title = "Deprecate JSON_AS_ASCII in config.py"
        body = "Calling `app.json.ensure_ascii` should be preferred."
        labels = ["enhancement", "good first issue"]
        keywords = extract_keywords(title, body, labels)
        self.assertIn("config.py", keywords)
        self.assertIn("app.json.ensure_ascii", keywords)
        self.assertIn("json_as_ascii", keywords)

    def test_ignored_paths(self):
        self.assertTrue(is_ignored_path("node_modules/package/index.js"))
        self.assertTrue(is_ignored_path(".git/HEAD"))
        self.assertTrue(is_ignored_path("dist/bundle.min.js"))
        self.assertTrue(is_ignored_path("assets/logo.png"))
        self.assertFalse(is_ignored_path("src/flask/config.py"))

    def test_rank_files(self):
        file_tree = [
            "src/flask/config.py",
            "src/flask/app.py",
            "docs/index.rst",
            "node_modules/express/index.js",
        ]
        keywords = ["config", "flask"]
        ranked = rank_relevant_files(file_tree, keywords, top_n=2)
        self.assertTrue(len(ranked) > 0)
        top_path = ranked[0]["path"]
        self.assertEqual(top_path, "src/flask/config.py")

    def test_snippet_extraction(self):
        content = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "def configure_json_ascii():\n"
            "    warn_deprecation('JSON_AS_ASCII is deprecated')\n"
            "    return True\n"
        )
        snippets = extract_evidence_snippets(content, ["json_as_ascii"], max_snippets=1, window_lines=2)
        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0]["confidence_type"], "verified")
        self.assertIn("JSON_AS_ASCII", snippets[0]["snippet"])


class TestAIEngine(unittest.TestCase):
    def test_pydantic_schema_validation(self):
        analysis = get_demo_analysis()
        self.assertIsInstance(analysis, IssueAnalysisResult)
        self.assertEqual(analysis.issue_title, "Proxy authentication bug")
        self.assertTrue(len(analysis.problem_hypotheses) >= 2)
        self.assertTrue(len(analysis.relevant_files) >= 1)
        self.assertTrue(len(analysis.implementation_plan) >= 1)
        self.assertTrue(len(analysis.suggested_tests) >= 1)
        self.assertTrue(len(analysis.contribution_checklist) >= 1)

    def test_clean_json_response(self):
        engine = GemmaEngine()
        raw_markdown = '```json\n{"issue_title": "Test", "issue_summary": "Summary"}\n```'
        cleaned = engine.clean_json_response(raw_markdown)
        self.assertTrue(cleaned.startswith("{"))
        self.assertTrue(cleaned.endswith("}"))

    def test_grounded_offline_synthesis(self):
        engine = GemmaEngine()
        issue_meta = {
            "number": 999,
            "title": "Fix buffer overflow in parser",
            "body": "When parsing malformed tokens, parser crashes.",
            "labels": ["bug"],
            "state": "open",
            "author": "tester",
        }
        evidence_list = [
            {
                "path": "src/parser.c",
                "score": 10.0,
                "has_content": True,
                "start_line": 50,
                "end_line": 65,
                "confidence_type": "verified",
                "why_relevant": "Contains token parsing loop",
            }
        ]
        result = engine.analyze_issue("org/parser", issue_meta, "", [], evidence_list, use_demo_fallback=True)
        self.assertIsInstance(result, IssueAnalysisResult)
        self.assertEqual(result.relevant_files[0].file_path, "src/parser.c")
        self.assertEqual(result.relevant_files[0].confidence_type, "verified")


class TestBenchmarkData(unittest.TestCase):
    def test_sample_issues_exist(self):
        self.assertIn("pallets/flask#5000", SAMPLE_ISSUES)
        self.assertIn("psf/requests#4200", SAMPLE_ISSUES)
        flask_sample = SAMPLE_ISSUES["pallets/flask#5000"]
        self.assertEqual(flask_sample["issue_number"], 5000)
        self.assertTrue(len(flask_sample["verified_evidence"]) > 0)


if __name__ == "__main__":
    unittest.main()
