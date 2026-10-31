"""Demo Data Module for IssueLens.

Provides offline fallback and demonstration fixtures for live presentations,
ensuring the application is fully functional even when offline or GitHub rate limits apply.
"""

from typing import List
from github_client import IssueData, RepoMetadata, FileSnippet
from ai_engine import (
    IssueAnalysisResult,
    FileEvidenceItem,
    ImplementationStep,
    InvestigationStep,
    TestCaseItem,
    ChecklistItem,
)

DEMO_REPO_URL = "https://github.com/psf/requests"
DEMO_ISSUE_URL = "https://github.com/psf/requests/issues/6027"


def get_demo_repo_metadata() -> RepoMetadata:
    """Return realistic demo repository metadata for psf/requests."""
    return RepoMetadata(
        owner="psf",
        name="requests",
        full_name="psf/requests",
        description="A simple, yet elegant, HTTP library for Python.",
        default_branch="main",
        language="Python",
        stars=52400,
        forks=9300,
        open_issues=180,
        html_url=DEMO_REPO_URL,
    )


def get_demo_issue_data() -> IssueData:
    """Return realistic demo issue data for psf/requests#6027."""
    return IssueData(
        owner="psf",
        repo="requests",
        number=6027,
        title="Proxy authentication bug",
        body=(
            "When using a proxy with basic authentication (`http://user:pass@proxy:8080`), "
            "the `Proxy-Authorization` header is improperly stripped after following a 302 redirect "
            "to another host, causing subsequent requests to fail with HTTP 407 Proxy Authentication Required."
        ),
        state="open",
        html_url=DEMO_ISSUE_URL,
        author="sigmavirus24",
        created_at="2023-02-15T14:22:00Z",
        updated_at="2023-02-16T09:10:00Z",
        labels=["bug", "security", "proxies"],
        comments_count=6,
        top_comments=[
            "Confirmed: `SessionRedirectMixin.rebuild_proxies` does not preserve proxy authorization when redirecting across domains.",
            "We should ensure `Proxy-Authorization` headers persist for proxy connections regardless of destination URL redirects."
        ],
        is_pull_request=False,
    )


def get_demo_snippets() -> List[FileSnippet]:
    """Return verified repository code snippets for psf/requests#6027."""
    snippet_content = (
        " 280 |     def rebuild_proxies(self, prepared_request, proxies):\n"
        " 281 |         \"\"\"This method re-evaluates the proxy configuration by\n"
        " 282 |         considering the redirected URL.\n"
        " 283 |         \"\"\"\n"
        " 284 |         headers = prepared_request.headers\n"
        " 285 |         url = prepared_request.url\n"
        " 286 |         scheme = urlparse(url).scheme\n"
        " 287 |         new_proxies = resolve_proxies(prepared_request, proxies, self.trust_env)\n"
        " 288 |\n"
        " 289 |         if 'Proxy-Authorization' in headers and should_strip_auth(url):\n"
        " 290 |             del headers['Proxy-Authorization']\n"
        " 291 |         return new_proxies"
    )
    return [
        FileSnippet(
            path="src/requests/sessions.py",
            content=snippet_content,
            start_line=280,
            end_line=291,
            total_lines=750,
            is_truncated=False,
            evidence_reason="Handles proxy reconstruction and Proxy-Authorization stripping on HTTP redirect.",
        ),
        FileSnippet(
            path="src/requests/adapters.py",
            content=(
                " 410 |     def proxy_headers(self, proxy):\n"
                " 411 |         \"\"\"Returns a dictionary of the headers to add to any request sent\n"
                " 412 |         through a proxy. This is used when connecting to an HTTP proxy.\n"
                " 413 |         \"\"\"\n"
                " 414 |         headers = {}\n"
                " 415 |         username, password = get_auth_from_url(proxy)\n"
                " 416 |         if username:\n"
                " 417 |             headers['Proxy-Authorization'] = _basic_auth_str(username, password)\n"
                " 418 |         return headers"
            ),
            start_line=410,
            end_line=418,
            total_lines=580,
            is_truncated=False,
            evidence_reason="Generates Proxy-Authorization basic auth headers for proxy connections.",
        ),
    ]


def get_demo_analysis() -> IssueAnalysisResult:
    """Return complete, grounded IssueAnalysisResult for psf/requests#6027."""
    return IssueAnalysisResult(
        issue_title="Proxy authentication bug",
        issue_summary=(
            "Requests inadvertently removes the `Proxy-Authorization` header during HTTP redirects "
            "via `SessionRedirectMixin.rebuild_proxies`, causing subsequent redirected requests through "
            "an authenticated proxy to fail with HTTP 407."
        ),
        beginner_explanation=(
            "Imagine driving through a tollbooth tunnel (the proxy) to reach your destination website. "
            "You hand the toll operator your access ticket (`Proxy-Authorization`). If the website sends "
            "you to a new webpage (a redirect), Requests mistakenly throws away your toll ticket, thinking "
            "it was meant for the website instead of the tunnel operator. As a result, the tunnel stops you "
            "with a 407 error. The fix ensures Requests keeps your toll ticket as long as you're using the same proxy tunnel."
        ),
        what_is_known=(
            "- Issue reported by maintainer @sigmavirus24 in psf/requests #6027.\n"
            "- Triggered when following a 302 redirect through an authenticated HTTP proxy.\n"
            "- Server returns HTTP 407 (Proxy Authentication Required) on the redirected hop."
        ),
        what_is_observed_in_code=(
            "- In `src/requests/sessions.py` line 289-290, `rebuild_proxies` checks `should_strip_auth(url)` "
            "and deletes `Proxy-Authorization`.\n"
            "- `should_strip_auth` was designed for origin `Authorization` headers, not proxy tunnel credentials.\n"
            "- `src/requests/adapters.py` lines 414-418 builds the initial `Proxy-Authorization` header."
        ),
        what_is_hypothesis=(
            "- Hypothesis 1: `should_strip_auth` incorrectly treats proxy tunnel credentials as origin credentials.\n"
            "- Hypothesis 2: Proxy credentials should only be stripped if the redirect switches to a different, untrusted proxy or bypasses the proxy entirely."
        ),
        what_to_investigate_next=(
            "1. Inspect `src/requests/sessions.py` around line 289 to decouple origin auth stripping from proxy auth stripping.\n"
            "2. Verify whether `new_proxies` uses the same proxy host before dropping `Proxy-Authorization`.\n"
            "3. Run `pytest tests/test_requests.py` with mock proxy redirect fixtures."
        ),
        problem_hypotheses=[
            "Hypothesis: `should_strip_auth` inappropriately strips `Proxy-Authorization` when redirected between different hosts on the same proxy tunnel.",
            "Hypothesis: Origin domain changes should only strip `Authorization`, while `Proxy-Authorization` must persist as long as the proxy host is unchanged.",
        ],
        relevant_files=[
            FileEvidenceItem(
                file_path="src/requests/sessions.py",
                confidence_type="verified",
                relationship="VERIFIED",
                why_relevant="Contains rebuild_proxies logic where Proxy-Authorization is stripped during redirect handling.",
                why_related="Contains rebuild_proxies logic where Proxy-Authorization is stripped during redirect handling.",
                code_snippet_reference="Lines 280-291: rebuild_proxies method",
                code_snippet=(
                    " 289 |         if 'Proxy-Authorization' in headers and should_strip_auth(url):\n"
                    " 290 |             del headers['Proxy-Authorization']\n"
                    " 291 |         return new_proxies"
                ),
            ),
            FileEvidenceItem(
                file_path="src/requests/adapters.py",
                confidence_type="verified",
                relationship="VERIFIED",
                why_relevant="Defines proxy_headers which creates the initial Proxy-Authorization credentials.",
                why_related="Defines proxy_headers which creates the initial Proxy-Authorization credentials.",
                code_snippet_reference="Lines 410-418: proxy_headers method",
                code_snippet=(
                    " 415 |         username, password = get_auth_from_url(proxy)\n"
                    " 416 |         if username:\n"
                    " 417 |             headers['Proxy-Authorization'] = _basic_auth_str(username, password)"
                ),
            ),
            FileEvidenceItem(
                file_path="tests/test_requests.py",
                confidence_type="verified",
                relationship="VERIFIED",
                why_relevant="Test suite containing session redirect and proxy test cases.",
                why_related="Test suite containing session redirect and proxy test cases.",
                code_snippet_reference="test_redirect_strips_auth test function",
                code_snippet=(
                    " 501 | def test_proxy_auth_preserved_on_redirect():\n"
                    " 502 |     session = requests.Session()\n"
                    " 503 |     # Test redirect preserving proxy authentication"
                ),
            ),
        ],
        investigation_steps=[
            InvestigationStep(
                step_number=1,
                action="Review rebuild_proxies implementation",
                details="Open `src/requests/sessions.py` at line 280 and examine how `headers` are modified on redirect.",
            ),
            InvestigationStep(
                step_number=2,
                action="Differentiate origin auth from proxy auth",
                details="Check `SessionRedirectMixin.rebuild_auth` vs `rebuild_proxies` to determine header ownership.",
            ),
            InvestigationStep(
                step_number=3,
                action="Run test suite locally",
                details="Execute `pytest tests/test_requests.py` to ensure existing redirect behavior passes.",
            ),
        ],
        implementation_plan=[
            ImplementationStep(
                step_number=1,
                target_file="src/requests/sessions.py",
                description="Preserve Proxy-Authorization header if the resolved proxy host has not changed.",
                code_change_summary="Only strip Proxy-Authorization if the proxy URL itself changed or was removed.",
            ),
            ImplementationStep(
                step_number=2,
                target_file="tests/test_requests.py",
                description="Add unit test verifying Proxy-Authorization header persists across 302 redirect.",
                code_change_summary="Assert 'Proxy-Authorization' in req.headers after following redirect through same proxy.",
            ),
        ],
        suggested_tests=[
            TestCaseItem(
                expected_behavior="Proxy-Authorization header persists when redirecting between different domains through the same proxy",
                input_scenario="Session with proxy auth following redirect from 'http://example.com' to 'http://other.com'",
                expected_output="Request to 'http://other.com' retains 'Proxy-Authorization: Basic ...' header",
                test_location="tests/test_requests.py::test_proxy_auth_persists_on_redirect",
            ),
            TestCaseItem(
                expected_behavior="Proxy-Authorization header is stripped if redirect bypasses the proxy",
                input_scenario="Redirect to host in NO_PROXY environment variable",
                expected_output="Proxy-Authorization header is deleted to prevent leaking credentials",
                test_location="tests/test_requests.py::test_proxy_auth_stripped_when_proxy_bypassed",
            ),
        ],
        files_to_investigate=[
            "src/requests/sessions.py",
            "src/requests/adapters.py",
            "tests/test_requests.py",
        ],
        tests_to_run=[
            "pytest tests/test_requests.py -k test_redirect",
            "pytest tests/test_requests.py -k test_proxy",
        ],
        documentation_to_inspect=[
            "docs/user/advanced.rst (Proxies section)",
            "CONTRIBUTING.md",
        ],
        potential_regressions=[
            "Accidental leakage of Proxy-Authorization to direct origins if proxy is bypassed on redirect",
            "Incompatibility with custom Transport Adapters overriding rebuild_proxies",
        ],
        pull_request_preparation=[
            "Create feature branch: `git checkout -b fix/proxy-auth-redirect`",
            "Run test suite: `pytest` with zero warnings",
            "Run linter: `flake8` or `ruff` per project rules",
            "Format PR title: `Preserve Proxy-Authorization across redirects on same proxy (#6027)`",
        ],
        contribution_checklist=[
            ChecklistItem(
                category="Files to Investigate",
                task="Inspect src/requests/sessions.py",
                details="Verify how rebuild_proxies determines whether to strip Proxy-Authorization.",
            ),
            ChecklistItem(
                category="Tests to Run",
                task="Run pytest tests/test_requests.py",
                details="Verify all existing proxy and redirect tests pass cleanly before making changes.",
            ),
            ChecklistItem(
                category="Documentation to Inspect",
                task="Inspect docs/user/advanced.rst",
                details="Check proxy documentation and ensure behavior aligns with documented expectations.",
            ),
            ChecklistItem(
                category="Potential Regressions",
                task="Verify NO_PROXY behavior",
                details="Ensure credentials are still stripped when redirected to a destination in NO_PROXY.",
            ),
            ChecklistItem(
                category="Pull Request Preparation",
                task="Prepare focused commit and link issue",
                details="Use `Fixes #6027` in PR description and follow Requests contributor guidelines.",
            ),
        ],
        confidence_and_limitations=(
            "High confidence (95%). The root cause is directly localized to lines 289-290 in `src/requests/sessions.py`. "
            "Limitation: Edge cases where proxy tunneling (CONNECT) vs standard forward proxying differ should be verified against urllib3."
        ),
        raw_model_name="gemma-4-26b-a4b-it",
    )
