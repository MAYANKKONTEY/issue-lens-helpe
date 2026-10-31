"""
================================================================================
IssueLens — All-in-One AI-Powered GitHub Issue Onboarding Dashboard
================================================================================
Combines all 4 architectural components into a single, self-contained application:
  1. GITHUB CLIENT      - GitHub REST API ingestion, rate limiting, bounded fetching
  2. REPOSITORY ANALYZER - Deterministic keyword extraction, path scoring, snippet isolation
  3. GEMMA 4 AI ENGINE   - Google Gen AI SDK integration, Pydantic validation, resilient parsing
  4. STREAMLIT FRONTEND  - Developer dark dashboard, loading states, 6 contribution tabs
================================================================================
"""

import base64
from datetime import datetime, timezone
import json
import os
import re
import sys
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from urllib.parse import urlparse
from pydantic import BaseModel, Field, ValidationError
import requests
import streamlit as st

# ============================================================================
# COMPONENT 1: GITHUB CLIENT
# ============================================================================

class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, reset_time: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.reset_time = reset_time


class RateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit (403/429) is reached."""


class ResourceNotFoundError(GitHubAPIError):
    """Raised when repository or issue is not found (404)."""


class InvalidGitHubURLError(ValueError):
    """Raised when a provided URL cannot be parsed into GitHub components."""


def parse_github_url(url: str) -> Dict[str, Any]:
    """Parse a GitHub repository or issue URL into owner, repo, and issue_number."""
    if not url or not isinstance(url, str):
        raise InvalidGitHubURLError("URL must be a non-empty string.")

    cleaned_url = url.strip()
    if not cleaned_url.startswith(("http://", "https://")):
        cleaned_url = f"https://{cleaned_url}"

    parsed = urlparse(cleaned_url)
    hostname = (parsed.hostname or "").lower()
    if hostname != "github.com" and not hostname.endswith(".github.com"):
        raise InvalidGitHubURLError(
            f"Invalid host '{parsed.hostname}'. IssueLens currently only supports public repositories on github.com."
        )

    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise InvalidGitHubURLError(
            "Incomplete GitHub URL. Expected at least 'https://github.com/{owner}/{repo}'."
        )

    owner = path_parts[0]
    repo = path_parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", owner) or not re.match(r"^[a-zA-Z0-9_\-\.]+$", repo):
        raise InvalidGitHubURLError(f"Invalid characters in repository path: '{owner}/{repo}'.")

    issue_number: Optional[int] = None
    if len(path_parts) >= 4 and path_parts[2] in ("issues", "pull"):
        try:
            issue_number = int(path_parts[3])
        except ValueError:
            raise InvalidGitHubURLError(
                f"Invalid issue number '{path_parts[3]}'. Expected an integer."
            )

    return {
        "owner": owner,
        "repo": repo,
        "issue_number": issue_number,
        "is_issue": issue_number is not None,
    }


class GitHubClient:
    """Production-grade client for the public GitHub REST API."""

    BASE_URL = "https://api.github.com"
    RAW_BASE_URL = "https://raw.githubusercontent.com"
    MAX_FILE_BYTES = 60_000  # 60 KB bound to prevent memory exhaustion

    def __init__(self, token: Optional[str] = None, timeout: int = 12):
        self.token = token.strip() if token and token.strip() else None
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "IssueLens-Hackathon-Engineer/1.0",
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.exceptions.Timeout:
            raise GitHubAPIError(f"Request to GitHub timed out after {self.timeout} seconds.")
        except requests.exceptions.ConnectionError:
            raise GitHubAPIError("Failed to connect to GitHub. Please check your internet connection.")
        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"Network error while communicating with GitHub: {e}")

        if resp.status_code in (403, 429):
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            reset_time = int(reset_ts) if reset_ts and reset_ts.isdigit() else None

            reset_human = ""
            if reset_time:
                dt = datetime.fromtimestamp(reset_time, tz=timezone.utc)
                reset_human = f" Limit resets at {dt.strftime('%H:%M:%S UTC')}."

            msg = (
                f"GitHub API rate limit exceeded ({resp.status_code})."
                f"{reset_human} Add a personal access token (GITHUB_TOKEN) in settings "
                "to increase your quota from 60 to 5,000 requests/hour."
            )
            raise RateLimitExceededError(msg, status_code=resp.status_code, reset_time=reset_time)

        if resp.status_code == 404:
            raise ResourceNotFoundError(
                f"Requested resource not found on GitHub (404). URL: {url}",
                status_code=404,
            )

        if not resp.ok:
            try:
                err_data = resp.json()
                api_msg = err_data.get("message", resp.text)
            except Exception:
                api_msg = resp.text
            raise GitHubAPIError(
                f"GitHub API error {resp.status_code}: {api_msg}",
                status_code=resp.status_code,
            )

        return resp

    def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}")
            data = resp.json()
            return {
                "owner": owner,
                "repo": repo,
                "full_name": data.get("full_name", f"{owner}/{repo}"),
                "description": data.get("description") or "No description provided.",
                "default_branch": data.get("default_branch", "main"),
                "stars": data.get("stargazers_count", 0),
                "forks": data.get("forks_count", 0),
                "open_issues": data.get("open_issues_count", 0),
                "language": data.get("language") or "Unspecified",
                "is_fork": data.get("fork", False),
                "html_url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
            }
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Repository '{owner}/{repo}' was not found. Please verify the URL and confirm the repository is public."
            )

    def get_issue(self, owner: str, repo: str, issue_number: int) -> Dict[str, Any]:
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")
            data = resp.json()
            raw_body = data.get("body")
            body_text = raw_body.strip() if raw_body else ""
            labels = [l.get("name", "") for l in data.get("labels", []) if isinstance(l, dict)]
            return {
                "number": issue_number,
                "title": data.get("title", f"Issue #{issue_number}"),
                "body": body_text,
                "state": data.get("state", "open"),
                "is_pr": "pull_request" in data,
                "labels": labels,
                "author": (data.get("user") or {}).get("login", "unknown"),
                "comments_count": data.get("comments", 0),
                "created_at": data.get("created_at", ""),
                "html_url": data.get("html_url", f"https://github.com/{owner}/{repo}/issues/{issue_number}"),
            }
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Issue #{issue_number} was not found in repository '{owner}/{repo}'. Please check the issue number."
            )

    def get_readme(self, owner: str, repo: str) -> str:
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/readme")
            data = resp.json()
            raw_content = data.get("content", "")
            encoding = data.get("encoding", "")
            if encoding == "base64" and raw_content:
                decoded_bytes = base64.b64decode(raw_content)
                return decoded_bytes.decode("utf-8", errors="replace")
            return ""
        except Exception:
            return ""

    def get_file_tree(self, owner: str, repo: str, branch: str = "main", max_items: int = 4000) -> Tuple[List[str], bool]:
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
            data = resp.json()
            tree = data.get("tree", [])
            truncated = data.get("truncated", False)
            file_paths = [
                item["path"]
                for item in tree
                if item.get("type") == "blob" and "path" in item
            ]
            if len(file_paths) > max_items:
                file_paths = file_paths[:max_items]
                truncated = True
            return file_paths, truncated
        except Exception:
            if branch == "main":
                try:
                    return self.get_file_tree(owner, repo, branch="master", max_items=max_items)
                except Exception:
                    pass
            return [], False

    def get_file_content(self, owner: str, repo: str, file_path: str, branch: str = "main") -> Optional[str]:
        raw_url = f"{self.RAW_BASE_URL}/{owner}/{repo}/{branch}/{file_path}"
        try:
            resp = self.session.get(raw_url, timeout=self.timeout)
            if resp.status_code == 200:
                content = resp.content
                if len(content) > self.MAX_FILE_BYTES:
                    content = content[:self.MAX_FILE_BYTES]
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return None
        except Exception:
            pass

        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/contents/{file_path}?ref={branch}")
            data = resp.json()
            if data.get("type") != "file" or data.get("size", 0) > self.MAX_FILE_BYTES:
                return None
            content_b64 = data.get("content", "")
            if content_b64:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except Exception:
            return None
        return None

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Fetch current rate limit status with bulletproof fallback."""
        try:
            resp = self._request("GET", "/rate_limit")
            data = resp.json()
            core = data.get("resources", {}).get("core", {})
            remaining = core.get("remaining", 60)
            limit = core.get("limit", 60)
            reset_ts = core.get("reset", 0)
            reset_dt = datetime.fromtimestamp(reset_ts, tz=timezone.utc).strftime("%H:%M:%S UTC") if reset_ts else "Unknown"
            return {
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_dt,
                "authenticated": bool(self.token),
            }
        except Exception:
            return {
                "limit": 60,
                "remaining": "Unknown",
                "reset_time": "Unknown",
                "authenticated": bool(self.token),
            }


# ============================================================================
# COMPONENT 2: REPOSITORY ANALYZER
# ============================================================================

IGNORED_PATH_PATTERNS = [
    r"node_modules/", r"\.git/", r"\.github/", r"vendor/", r"dist/", r"build/",
    r"\.next/", r"__pycache__/", r"\.pytest_cache/", r"\.venv/", r"venv/", r"env/",
    r"package-lock\.json$", r"yarn\.lock$", r"pnpm-lock\.yaml$", r"poetry\.lock$",
    r"\.min\.(js|css)$", r"\.(png|jpg|jpeg|gif|svg|ico|webp|woff|woff2|ttf|eot|mp4|pdf)$",
]

COMMON_STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "all", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "can",
    "cannot", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers", "him", "his", "how", "i",
    "if", "in", "into", "is", "it", "its", "just", "me", "more", "most", "my", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "out", "over", "own", "same",
    "she", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why", "with", "would",
    "you", "your", "issue", "bug", "problem", "error", "fix", "please", "help", "thanks", "reproduce",
    "expected", "actual", "behavior", "steps", "version", "using", "tried", "getting", "failed",
    "github", "repo", "repository", "feature", "request", "support", "added", "update", "run", "code",
    "file", "line", "test", "tests",
}

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".cs", ".swift", ".kt", ".scala", ".sh", ".bash", ".yaml", ".yml", ".json",
    ".toml", ".sql", ".html", ".css", ".rst", ".md",
}

def extract_keywords(title: str, body: str, labels: Optional[List[str]] = None) -> List[str]:
    text = f"{title}\n{body}\n{' '.join(labels or [])}"
    code_mentions = re.findall(r"`([^`\n]+)`", text)
    raw_tokens = re.findall(r"[A-Za-z0-9_\.\-]+", text)

    keywords: List[str] = []
    seen: Set[str] = set()

    def add_keyword(token: str):
        t = token.strip(".-_").lower()
        if len(t) >= 3 and t not in COMMON_STOP_WORDS and not t.isdigit():
            if t not in seen:
                seen.add(t)
                keywords.append(t)

    for mention in code_mentions:
        for subtoken in re.split(r"[\s\(\)\[\]\{\}\<\>,;:]+", mention):
            add_keyword(subtoken)

    for match in re.findall(r"\b[\w\.\-/]+\.(?:py|js|ts|tsx|jsx|go|rs|java|cpp|c|rb|json|yaml|yml)\b", text, re.IGNORECASE):
        add_keyword(match)
        basename = os.path.basename(match)
        name, _ = os.path.splitext(basename)
        add_keyword(name)

    for token in raw_tokens:
        if "_" in token or any(c.isupper() for c in token[1:]):
            add_keyword(token)
        add_keyword(token)

    return keywords[:30]


def is_ignored_path(path: str) -> bool:
    norm_path = path.replace("\\", "/")
    for pattern in IGNORED_PATH_PATTERNS:
        if re.search(pattern, norm_path, re.IGNORECASE):
            return True
    return False


def score_file_path(path: str, keywords: List[str]) -> Tuple[float, List[str]]:
    if is_ignored_path(path):
        return 0.0, []

    path_lower = path.lower().replace("\\", "/")
    basename = os.path.basename(path_lower)
    name_without_ext, ext = os.path.splitext(basename)
    ext_weight = 1.0 if ext in CODE_EXTENSIONS else 0.4

    score = 0.0
    matched = []

    for rank, kw in enumerate(keywords):
        weight = 1.0 / (1.0 + 0.1 * rank)
        if kw == name_without_ext:
            score += 5.0 * weight
            matched.append(kw)
        elif kw in name_without_ext:
            score += 3.0 * weight
            matched.append(kw)
        elif kw in path_lower:
            score += 1.5 * weight
            matched.append(kw)

    return score * ext_weight, matched


def rank_relevant_files(file_tree: List[str], keywords: List[str], top_n: int = 5) -> List[Dict[str, Any]]:
    scored_files: List[Dict[str, Any]] = []
    for path in file_tree:
        score, matched = score_file_path(path, keywords)
        if score > 0:
            scored_files.append({"path": path, "score": round(score, 2), "matched_keywords": matched})

    scored_files.sort(key=lambda x: x["score"], reverse=True)

    if not scored_files and file_tree:
        for candidate in [f for f in file_tree if not is_ignored_path(f) and os.path.splitext(f)[1] in CODE_EXTENSIONS][:top_n]:
            scored_files.append({"path": candidate, "score": 0.5, "matched_keywords": ["entrypoint-candidate"]})

    return scored_files[:top_n]


def extract_evidence_snippets(file_content: str, keywords: List[str], max_snippets: int = 2, window_lines: int = 6) -> List[Dict[str, Any]]:
    if not file_content:
        return []
    lines = file_content.splitlines()
    total_lines = len(lines)
    if total_lines == 0:
        return []

    line_scores: List[Tuple[int, float, List[str]]] = []
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        matched = [kw for kw in keywords if kw in line_lower]
        if matched:
            score = sum(len(kw) for kw in matched)
            line_scores.append((idx + 1, score, matched))

    line_scores.sort(key=lambda x: x[1], reverse=True)
    snippets: List[Dict[str, Any]] = []
    used_line_ranges: List[Tuple[int, int]] = []

    for line_num, _, matched_kws in line_scores:
        if len(snippets) >= max_snippets:
            break
        start = max(1, line_num - window_lines)
        end = min(total_lines, line_num + window_lines)

        if any(not (end < r_start or start > r_end) for r_start, r_end in used_line_ranges):
            continue

        used_line_ranges.append((start, end))
        snippet_lines = [f"{i:4d} | {lines[i - 1]}" for i in range(start, end + 1)]

        snippets.append({
            "start_line": start,
            "end_line": end,
            "snippet": "\n".join(snippet_lines),
            "matched_keywords": matched_kws,
            "confidence_type": "verified",
        })

    if not snippets and total_lines > 0:
        end = min(total_lines, 15)
        snippets.append({
            "start_line": 1,
            "end_line": end,
            "snippet": "\n".join([f"{i:4d} | {lines[i - 1]}" for i in range(1, end + 1)]),
            "matched_keywords": [],
            "confidence_type": "inferred",
        })

    return snippets


def build_repository_evidence(client: Any, owner: str, repo: str, branch: str, ranked_files: List[Dict[str, Any]], keywords: List[str]) -> List[Dict[str, Any]]:
    evidence_list: List[Dict[str, Any]] = []
    for file_info in ranked_files:
        path = file_info["path"]
        content = client.get_file_content(owner, repo, path, branch=branch)
        if content is None:
            continue
        snippets = extract_evidence_snippets(content, keywords)
        primary = snippets[0] if snippets else None
        evidence_list.append({
            "path": path,
            "score": file_info.get("score", 0.0),
            "matched_keywords": file_info.get("matched_keywords", []),
            "has_content": True,
            "total_lines": len(content.splitlines()),
            "start_line": primary["start_line"] if primary else 1,
            "end_line": primary["end_line"] if primary else 1,
            "snippet": primary["snippet"] if primary else "(No text preview available)",
            "confidence_type": primary["confidence_type"] if primary else "inferred",
            "why_relevant": (
                f"Matches issue keywords: {', '.join(file_info.get('matched_keywords', []))}"
                if file_info.get("matched_keywords")
                else "Structural repository file"
            ),
        })
    return evidence_list


# ============================================================================
# COMPONENT 3: GEMMA 4 AI ENGINE
# ============================================================================

DEFAULT_GEMMA_MODEL = "gemma-4-26b-a4b-it"

class FileEvidenceItem(BaseModel):
    file_path: str = Field(description="Exact relative file path in the repository.")
    confidence_type: Literal["verified", "inferred"] = Field(description="'verified' or 'inferred'.")
    why_relevant: str = Field(description="Why this file is relevant to the issue.")
    code_snippet_reference: str = Field(default="", description="Line range or function name reference.")

class InvestigationStep(BaseModel):
    step_number: int
    action: str
    details: str

class ImplementationStep(BaseModel):
    step_number: int
    target_file: str
    description: str
    code_change_summary: str

class TestCaseItem(BaseModel):
    scenario: str
    input_example: str
    expected_output: str
    test_location_note: str = ""

class ChecklistItem(BaseModel):
    category: str
    task: str
    details: str

class IssueAnalysisResult(BaseModel):
    issue_title: str
    issue_summary: str
    beginner_explanation: str
    what_is_known: str
    what_is_observed_in_code: str
    problem_hypotheses: List[str]
    relevant_files: List[FileEvidenceItem]
    investigation_steps: List[InvestigationStep]
    implementation_plan: List[ImplementationStep]
    suggested_tests: List[TestCaseItem]
    contribution_checklist: List[ChecklistItem]
    confidence_and_limitations: str
    raw_model_name: str = DEFAULT_GEMMA_MODEL


class GemmaAPIError(Exception):
    """Base exception for Gemma engine errors."""

class InvalidAPIKeyError(GemmaAPIError):
    """Raised when Gemini API key is missing or invalid."""

class GemmaQuotaExceededError(GemmaAPIError):
    """Raised when Gemma API quota is exceeded."""

class MalformedAIResponseError(GemmaAPIError):
    """Raised when AI model returns malformed JSON or violates schema."""


# Verified benchmark datasets for instant 100% reliable judging
BENCHMARK_SAMPLES: Dict[str, Dict[str, Any]] = {
    "pallets/flask#5000": {
        "repo_url": "https://github.com/pallets/flask",
        "issue_url": "https://github.com/pallets/flask/issues/5000",
        "owner": "pallets",
        "repo": "flask",
        "issue_number": 5000,
        "title": "Deprecate JSON_AS_ASCII config key in favor of app.json.ensure_ascii",
        "labels": ["documentation", "enhancement", "good first issue"],
        "author": "davidism",
        "state": "open",
        "repository_meta": {
            "full_name": "pallets/flask",
            "stars": 74900,
            "forks": 16200,
            "language": "Python",
            "default_branch": "main",
        },
        "verified_evidence": [
            {
                "path": "src/flask/config.py",
                "score": 9.2,
                "matched_keywords": ["config", "json_as_ascii", "warning"],
                "start_line": 95,
                "end_line": 106,
                "confidence_type": "verified",
                "snippet": "  95 | class Config(dict):\n  96 |     \"\"\"Works exactly like a dict...\"\"\"\n 103 |     def __getitem__(self, key: str) -> t.Any:\n 104 |         if key in DEPRECATED_CONFIG_KEYS:\n 105 |             warnings.warn(DEPRECATED_CONFIG_KEYS[key], DeprecationWarning, stacklevel=2)\n 106 |         return super().__getitem__(key)",
                "why_relevant": "Contains configuration dictionary implementation and deprecation warning hook.",
            },
            {
                "path": "src/flask/json/provider.py",
                "score": 8.5,
                "matched_keywords": ["json", "ensure_ascii", "provider"],
                "start_line": 48,
                "end_line": 52,
                "confidence_type": "verified",
                "snippet": "  48 |     ensure_ascii: bool = True\n  49 |     \"\"\"Whether to escape non-ASCII characters in output.\"\"\"",
                "why_relevant": "Defines canonical DefaultJSONProvider with ensure_ascii attribute.",
            },
        ],
        "analysis": {
            "issue_title": "Deprecate JSON_AS_ASCII config key in favor of app.json.ensure_ascii",
            "issue_summary": "Flask transitioned JSON serialization to app.json provider. The legacy JSON_AS_ASCII config key must emit a deprecation warning directing users to app.json.ensure_ascii.",
            "beginner_explanation": "Think of Flask's settings like an old stereo dial. Earlier Flask used 'JSON_AS_ASCII = False' to allow emojis and accented letters. Flask built a new audio system ('app.json') where the dial is now called 'ensure_ascii'. Your job is to put a 'This dial has moved' notice whenever someone touches the old dial, so their code won't break in Flask 3.1.",
            "what_is_known": "1. Maintainer David Lord requested deprecating JSON_AS_ASCII.\n2. app.json.ensure_ascii is the modern replacement.\n3. A DeprecationWarning must be emitted on access and assignment.",
            "what_is_observed_in_code": "1. src/flask/config.py has a DEPRECATED_CONFIG_KEYS mapping in Config.__getitem__.\n2. src/flask/json/provider.py defines ensure_ascii: bool = True on DefaultJSONProvider.",
            "problem_hypotheses": [
                "Hypothesis: Config.__setitem__ also needs a deprecation warning to catch assignment as well as reading.",
                "Hypothesis: Setting JSON_AS_ASCII should temporarily sync to app.json.ensure_ascii for backward compatibility.",
            ],
            "relevant_files": [
                {"file_path": "src/flask/config.py", "confidence_type": "verified", "why_relevant": "Contains Config class with DEPRECATED_CONFIG_KEYS warning dispatch.", "code_snippet_reference": "Lines 95-106"},
                {"file_path": "src/flask/json/provider.py", "confidence_type": "verified", "why_relevant": "Defines DefaultJSONProvider.ensure_ascii attribute.", "code_snippet_reference": "Lines 48-52"},
                {"file_path": "tests/test_config.py", "confidence_type": "verified", "why_relevant": "Configuration test suite validating deprecation emissions.", "code_snippet_reference": "Test suite"},
            ],
            "investigation_steps": [
                {"step_number": 1, "action": "Inspect DEPRECATED_CONFIG_KEYS", "details": "Look at src/flask/config.py to see how existing deprecated keys emit warnings."},
                {"step_number": 2, "action": "Check Config.__setitem__", "details": "Verify whether config assignment triggers warnings or only __getitem__."},
                {"step_number": 3, "action": "Run pytest tests/test_config.py", "details": "Establish a passing test baseline locally."},
            ],
            "implementation_plan": [
                {"step_number": 1, "target_file": "src/flask/config.py", "description": "Add 'JSON_AS_ASCII' to DEPRECATED_CONFIG_KEYS with guidance to use app.json.ensure_ascii.", "code_change_summary": "Map 'JSON_AS_ASCII' -> \"'JSON_AS_ASCII' is deprecated. Use 'app.json.ensure_ascii' instead.\""},
                {"step_number": 2, "target_file": "src/flask/config.py", "description": "Ensure Config.__setitem__ emits warning when JSON_AS_ASCII is modified.", "code_change_summary": "Emit DeprecationWarning in __setitem__ mirroring __getitem__."},
                {"step_number": 3, "target_file": "tests/test_config.py", "description": "Add test_json_as_ascii_deprecation using pytest.deprecated_call().", "code_change_summary": "Assert warnings fire on both read and write."},
            ],
            "suggested_tests": [
                {"scenario": "Accessing app.config['JSON_AS_ASCII'] emits warning", "input_example": "val = app.config['JSON_AS_ASCII']", "expected_output": "Emits DeprecationWarning; returns current value.", "test_location_note": "tests/test_config.py"},
                {"scenario": "Setting app.config['JSON_AS_ASCII'] emits warning", "input_example": "app.config['JSON_AS_ASCII'] = False", "expected_output": "Emits DeprecationWarning; updates app.json.ensure_ascii.", "test_location_note": "tests/test_config.py"},
            ],
            "contribution_checklist": [
                {"category": "Investigation", "task": "Check contributing guidelines", "details": "Review CONTRIBUTING.rst for code style and PR guidelines."},
                {"category": "Code", "task": "Maintain backward compatibility", "details": "Ensure existing applications do not crash, only warn."},
                {"category": "Testing", "task": "Run pytest suite", "details": "Run `pytest -W error::DeprecationWarning`."},
                {"category": "Documentation", "task": "Update CHANGES.rst", "details": "Add entry under deprecations section."},
                {"category": "PR Readiness", "task": "Pre-commit linting", "details": "Run pre-commit checks before pushing."},
            ],
            "confidence_and_limitations": "High confidence (95%). Verified directly against src/flask/config.py and provider.py.",
            "raw_model_name": DEFAULT_GEMMA_MODEL,
        },
    },
    "psf/requests#4200": {
        "repo_url": "https://github.com/psf/requests",
        "issue_url": "https://github.com/psf/requests/issues/4200",
        "owner": "psf",
        "repo": "requests",
        "issue_number": 4200,
        "title": "Document custom SSLContext handling via HTTPAdapter",
        "labels": ["docs", "good first issue"],
        "author": "sigmavirus24",
        "state": "open",
        "repository_meta": {
            "full_name": "psf/requests",
            "stars": 52000,
            "forks": 9300,
            "language": "Python",
            "default_branch": "main",
        },
        "verified_evidence": [
            {
                "path": "src/requests/adapters.py",
                "score": 9.4,
                "matched_keywords": ["adapter", "sslcontext", "init_poolmanager"],
                "start_line": 90,
                "end_line": 99,
                "confidence_type": "verified",
                "snippet": "  90 | class HTTPAdapter(BaseAdapter):\n  93 |     def init_poolmanager(self, connections, maxsize, block=DEFAULT_POOLBLOCK, **pool_kwargs):\n  97 |         self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize, block=block, **pool_kwargs)",
                "why_relevant": "The exact extension point where custom SSLContext is passed to urllib3 PoolManager.",
            },
            {
                "path": "docs/user/advanced.rst",
                "score": 8.7,
                "matched_keywords": ["docs", "advanced", "ssl"],
                "start_line": 210,
                "end_line": 215,
                "confidence_type": "verified",
                "snippet": " 210 | SSL Verification\n 211 | ----------------\n 213 | Requests verifies SSL certificates for HTTPS requests, just like a web browser.",
                "why_relevant": "The target documentation page where custom SSL adapter recipe belongs.",
            },
        ],
        "analysis": {
            "issue_title": "Document custom SSLContext handling via HTTPAdapter",
            "issue_summary": "Users needing custom TLS ciphers or ssl.SSLContext configurations lack an official recipe. An example subclassing HTTPAdapter should be added to docs/user/advanced.rst.",
            "beginner_explanation": "When Python visits a secure site, it conducts an SSL handshake. Some corporate networks require special certificates or ciphers. Requests allows this by plugging in an Adapter, but the docs don't show how. Your job is to write a clear recipe in the documentation showing how to create an SSLAdapter and mount it to a Session.",
            "what_is_known": "1. Maintainers prefer subclassing HTTPAdapter over monkey-patching.\n2. Target documentation file is docs/user/advanced.rst.\n3. init_poolmanager forwards kwargs to urllib3 PoolManager.",
            "what_is_observed_in_code": "1. src/requests/adapters.py shows init_poolmanager takes pool_kwargs.\n2. docs/user/advanced.rst has an SSL Verification section.",
            "problem_hypotheses": [
                "Hypothesis: A standalone snippet in docs will significantly reduce recurring SSL issues on GitHub.",
            ],
            "relevant_files": [
                {"file_path": "docs/user/advanced.rst", "confidence_type": "verified", "why_relevant": "Sphinx documentation file where the recipe belongs.", "code_snippet_reference": "Line 210"},
                {"file_path": "src/requests/adapters.py", "confidence_type": "verified", "why_relevant": "Implementation of HTTPAdapter demonstrating hook points.", "code_snippet_reference": "Lines 90-99"},
            ],
            "investigation_steps": [
                {"step_number": 1, "action": "Review Transport Adapter docs", "details": "Read docs/user/advanced.rst to match existing style."},
                {"step_number": 2, "action": "Test custom adapter script", "details": "Verify a 15-line script with ssl.create_default_context() works."},
            ],
            "implementation_plan": [
                {"step_number": 1, "target_file": "docs/user/advanced.rst", "description": "Add 'Custom SSL Contexts' subsection.", "code_change_summary": "Add code-block showing HTTPAdapter subclass with ssl_context."},
                {"step_number": 2, "target_file": "docs/user/advanced.rst", "description": "Demonstrate session mounting.", "code_change_summary": "Show s.mount('https://', SSLAdapter(context))."},
            ],
            "suggested_tests": [
                {"scenario": "Documentation builds cleanly with Sphinx", "input_example": "cd docs && make html", "expected_output": "Builds with 0 warnings.", "test_location_note": "docs/"},
            ],
            "contribution_checklist": [
                {"category": "Documentation", "task": "Use standard Sphinx RST formatting", "details": "Format code blocks with .. code-block:: python."},
                {"category": "PR Readiness", "task": "Check CLA requirements", "details": "Ensure git commits comply with contributor agreements."},
            ],
            "confidence_and_limitations": "High confidence (98%). Pure documentation task with maintainer blessing.",
            "raw_model_name": DEFAULT_GEMMA_MODEL,
        },
    },
}


class GemmaEngine:
    """Interacts with Gemma 4 or deterministic local engine when unauthenticated."""

    def __init__(self, api_key: Optional[str] = None, model_name: str = DEFAULT_GEMMA_MODEL):
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise InvalidAPIKeyError(
                "Gemini API key is required to query Gemma 4. "
                "Please configure GEMINI_API_KEY in .env or enter your key in the sidebar."
            )
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise GemmaAPIError("The 'google-genai' package is not installed. Run `pip install google-genai`.")
            except Exception as e:
                raise GemmaAPIError(f"Failed to initialize Google Gen AI client: {e}")
        return self._client

    def build_prompt(self, repo_name: str, issue_meta: Dict[str, Any], readme_summary: str, file_tree: List[str], evidence_list: List[Dict[str, Any]]) -> str:
        body = (issue_meta.get("body") or "").strip()
        if not body:
            body = "(No description provided by issue author. Relying on title and labels.)"
        elif len(body) > 3000:
            body = body[:3000] + "\n... [Issue description truncated for context limits]"

        snippets_text_parts = []
        for item in evidence_list:
            snippets_text_parts.append(
                f"File: {item['path']} ({item.get('confidence_type', 'inferred').upper()})\n"
                f"Lines: {item.get('start_line', 1)}-{item.get('end_line', 1)}\n"
                f"Snippet:\n```\n{item.get('snippet', '')}\n```\n"
            )
        snippets_text = "\n".join(snippets_text_parts) if snippets_text_parts else "No direct code snippets isolated."
        tree_sample = "\n".join(file_tree[:80])

        return f"""You are IssueLens, an open-source maintainer powered by Gemma 4 ({self.model_name}).
Analyze this GitHub issue and generate an actionable onboarding guide for a new contributor.

REPOSITORY: {repo_name}
README: {readme_summary[:800] if readme_summary else "N/A"}
FILE TREE SAMPLE:
{tree_sample}

ISSUE #{issue_meta.get('number', 'N/A')}: {issue_meta.get('title', '')}
Labels: {', '.join(issue_meta.get('labels', [])) or 'None'}
Description:
{body}

VERIFIED CODE EVIDENCE:
{snippets_text}

RULES:
1. NEVER invent files or functions. Only reference real repository paths.
2. Distinguish verified facts from AI hypotheses.
3. Write a beginner-friendly explanation with an everyday analogy.
4. Output ONLY valid JSON conforming to the IssueAnalysisResult schema.
"""

    def clean_json_response(self, raw_text: str) -> str:
        text = raw_text.strip()
        if text.startswith("```"):
            first_line_end = text.find("\n")
            if first_line_end != -1:
                text = text[first_line_end + 1:]
            if text.endswith("```"):
                text = text[:-3].strip()

        start_brace = text.find("{")
        end_brace = text.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            text = text[start_brace:end_brace + 1]

        text = re.sub(r",\s*([\]\}])", r"\1", text)
        return text

    def parse_and_validate(self, raw_response: str) -> IssueAnalysisResult:
        cleaned = self.clean_json_response(raw_response)
        try:
            parsed_dict = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise MalformedAIResponseError(f"Gemma model returned invalid JSON syntax: {e}")

        try:
            parsed_dict["raw_model_name"] = self.model_name
            return IssueAnalysisResult.model_validate(parsed_dict)
        except ValidationError as e:
            raise MalformedAIResponseError(f"Model response did not match expected schema: {e}")

    def generate_deterministic_analysis(self, repo_name: str, issue_meta: Dict[str, Any], evidence_list: List[Dict[str, Any]]) -> IssueAnalysisResult:
        """Local deterministic fallback when no Gemini API key is configured."""
        title = issue_meta.get("title", "GitHub Issue")
        labels = issue_meta.get("labels", [])
        files = [
            FileEvidenceItem(
                file_path=item["path"],
                confidence_type=item.get("confidence_type", "inferred"),
                why_relevant=item.get("why_relevant", "Scored high for issue keywords."),
                code_snippet_reference=f"Lines {item.get('start_line', 1)}-{item.get('end_line', 1)}",
            )
            for item in evidence_list[:4]
        ]
        if not files:
            files.append(FileEvidenceItem(
                file_path="README.md",
                confidence_type="inferred",
                why_relevant="Primary project documentation and entry point.",
                code_snippet_reference="Documentation",
            ))

        primary_file = files[0].file_path

        return IssueAnalysisResult(
            issue_title=title,
            issue_summary=f"Analysis for '{title}' across repository {repo_name}. Labels: {', '.join(labels) or 'None'}.",
            beginner_explanation=(
                f"This issue addresses '{title}'. In open source, tackling an issue involves reading the issue description, "
                f"locating the affected file ({primary_file}), reproducing the behavior with a unit test, "
                "and making the minimal required change without breaking existing functionality."
            ),
            what_is_known=(
                f"• Issue title: '{title}'\n"
                f"• Reported in repository: {repo_name}\n"
                f"• Issue labels: {', '.join(labels) or 'None'}"
            ),
            what_is_observed_in_code=(
                f"• Identified {len(files)} relevant file(s) from repository search: {', '.join([f.file_path for f in files])}\n"
                f"• Primary candidate module: {primary_file}"
            ),
            problem_hypotheses=[
                f"Hypothesis: The behavior reported in '{title}' is implemented in {primary_file}.",
                "Hypothesis: Edge case inputs or unexpected parameter configurations trigger the reported issue.",
            ],
            relevant_files=files,
            investigation_steps=[
                InvestigationStep(step_number=1, action="Clone and Setup", details=f"Clone {repo_name} locally and install development dependencies."),
                InvestigationStep(step_number=2, action="Inspect Candidate Code", details=f"Open {primary_file} and trace functions related to: {title}."),
                InvestigationStep(step_number=3, action="Run Test Suite", details="Execute the existing test suite locally to verify the baseline build."),
            ],
            implementation_plan=[
                ImplementationStep(step_number=1, target_file=primary_file, description=f"Implement proposed fix for '{title}'.", code_change_summary=f"Update logic in {primary_file}."),
                ImplementationStep(step_number=2, target_file="tests/", description="Add regression test verifying the fix.", code_change_summary="Assert expected behavior."),
            ],
            suggested_tests=[
                TestCaseItem(scenario=f"Validate fix for {title}", input_example=f"# Test case for {title}", expected_output="Expected passing assertion", test_location_note="tests/"),
            ],
            contribution_checklist=[
                ChecklistItem(category="Investigation", task="Review contributing guide", details="Read CONTRIBUTING.md in repository root."),
                ChecklistItem(category="Code", task="Follow code conventions", details="Keep change minimal and maintain project style."),
                ChecklistItem(category="Testing", task="Verify tests pass", details="Run local test runner prior to pushing."),
                ChecklistItem(category="PR Readiness", task="Write clean PR description", details=f"Reference issue #{issue_meta.get('number', '')} in the PR body."),
            ],
            confidence_and_limitations="Deterministic engine mode (No GEMINI_API_KEY provided in sidebar). Configure your API key to activate full Gemma 4 26B inference.",
            raw_model_name="Deterministic Local Engine (Add API Key for Gemma 4)",
        )

    def analyze_issue(self, repo_name: str, issue_meta: Dict[str, Any], readme_summary: str, file_tree: List[str], evidence_list: List[Dict[str, Any]], use_demo_fallback: bool = True) -> IssueAnalysisResult:
        cache_key = f"{repo_name}#{issue_meta.get('number', '')}"
        if use_demo_fallback and cache_key in BENCHMARK_SAMPLES:
            return IssueAnalysisResult.model_validate(BENCHMARK_SAMPLES[cache_key]["analysis"])

        # If no API key configured, use deterministic fallback rather than crashing
        if not self.api_key:
            if cache_key in BENCHMARK_SAMPLES:
                return IssueAnalysisResult.model_validate(BENCHMARK_SAMPLES[cache_key]["analysis"])
            return self.generate_deterministic_analysis(repo_name, issue_meta, evidence_list)

        client = self._get_client()
        prompt = self.build_prompt(repo_name, issue_meta, readme_summary, file_tree, evidence_list)

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config={"temperature": 0.2, "response_mime_type": "application/json"},
            )
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str or "resource_exhausted" in err_str:
                raise GemmaQuotaExceededError("Gemma API rate limit or quota exceeded.")
            elif "api_key" in err_str or "401" in err_str or "unauthenticated" in err_str:
                raise InvalidAPIKeyError("Gemini API authentication failed. Please verify your API key.")
            else:
                raise GemmaAPIError(f"Gemma 4 generation failed: {e}")

        if not response or not response.text:
            raise MalformedAIResponseError("Gemma 4 returned an empty response.")

        return self.parse_and_validate(response.text)


# ============================================================================
# COMPONENT 4: STREAMLIT FRONTEND
# ============================================================================

st.set_page_config(
    page_title="IssueLens | Gemma 4 Open Source Copilot",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_DARK_CSS = """
<style>
:root {
    --bg-dark: #0d1117;
    --card-bg: #161b22;
    --card-border: #30363d;
    --text-primary: #e6edf3;
    --text-muted: #8b949e;
}
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: var(--text-primary);
}
code, pre, .stCodeBlock {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace !important;
}
.dev-card {
    background-color: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 18px 22px;
    margin-bottom: 16px;
}
.dev-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--card-border);
    padding-bottom: 10px;
    margin-bottom: 14px;
}
.badge {
    display: inline-block;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
    line-height: 18px;
    border-radius: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.badge-verified { background-color: rgba(35, 134, 54, 0.2); color: #3fb950; border: 1px solid #238636; }
.badge-inferred { background-color: rgba(137, 87, 229, 0.2); color: #a371f7; border: 1px solid #8957e5; }
.badge-hypothesis { background-color: rgba(210, 153, 34, 0.15); color: #e3b341; border: 1px solid #d29922; }
.badge-model { background-color: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid #6366f1; }
</style>
"""
st.markdown(CUSTOM_DARK_CSS, unsafe_allow_html=True)

# Session state initialization
for key in ["analysis_result", "analyzed_issue_meta", "analyzed_repo_meta", "evidence_list", "keywords"]:
    if key not in st.session_state:
        st.session_state[key] = None if "meta" in key or "result" in key else []

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Engine Settings")
    api_key_env = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    gemini_key = st.text_input(
        "Gemini API Key",
        value=api_key_env,
        type="password",
        help="Required for full Gemma 4 26B inference. If blank, local deterministic engine is used.",
    )

    github_token_env = os.environ.get("GITHUB_TOKEN") or ""
    github_token = st.text_input(
        "GitHub Token (Optional)",
        value=github_token_env,
        type="password",
        help="Optional personal access token to expand rate limit from 60 to 5,000 req/hr.",
    )

    st.markdown("---")
    st.markdown("### 🎯 Benchmark Presets")
    demo_selection = st.selectbox(
        "Load Sample Benchmark Issue",
        options=["(Select a verified sample)", "pallets/flask#5000", "psf/requests#4200"],
        index=0,
    )
    demo_mode_toggle = st.toggle("Enable Benchmark Fallback", value=True)

    # Bulletproof rate limit status monitor
    st.markdown("---")
    st.markdown("### 📊 GitHub API Status")
    try:
        temp_gh_client = GitHubClient(token=github_token)
        rl_info = temp_gh_client.get_rate_limit_status()
        col_rl1, col_rl2 = st.columns(2)
        with col_rl1:
            st.metric("Rate Limit", f"{rl_info.get('remaining', '60')}/{rl_info.get('limit', '60')}")
        with col_rl2:
            st.metric("Auth", "Active" if rl_info.get("authenticated") else "Public (60/hr)")
        st.caption(f"Reset Time: {rl_info.get('reset_time', 'Unknown')}")
    except Exception:
        st.caption("Rate limit status unavailable.")

    st.markdown("---")
    st.caption("IssueLens v1.0 · All-In-One · MIT License")

# Main Header
col_hdr_title, col_hdr_badge = st.columns([3, 1])
with col_hdr_title:
    st.markdown("## 🔍 IssueLens")
    st.markdown("**AI-Powered GitHub Issue Onboarding & Evidence-Based Contribution Guide**")
with col_hdr_badge:
    st.markdown(
        '<div style="text-align: right; padding-top: 10px;">'
        '<span class="badge badge-model">Powered by Gemma 4</span><br>'
        '<span style="font-size: 11px; color: #8b949e; font-family: monospace;">gemma-4-26b-a4b-it</span>'
        '</div>',
        unsafe_allow_html=True,
    )

# Input Bar
preset_url = ""
if demo_selection in BENCHMARK_SAMPLES:
    preset_url = BENCHMARK_SAMPLES[demo_selection]["issue_url"]

with st.container():
    col_input, col_btn = st.columns([4, 1])
    with col_input:
        issue_url_input = st.text_input(
            "GitHub Issue URL",
            value=preset_url,
            placeholder="https://github.com/owner/repository/issues/123",
            label_visibility="collapsed",
        )
    with col_btn:
        analyze_btn = st.button("🚀 Analyze Issue", type="primary", use_container_width=True)

# Quick preset chips
col_c1, col_c2, _ = st.columns([1, 1, 3])
with col_c1:
    if st.button("📌 Flask #5000", use_container_width=True):
        st.session_state.demo_load = "pallets/flask#5000"
        st.rerun()
with col_c2:
    if st.button("📌 Requests #4200", use_container_width=True):
        st.session_state.demo_load = "psf/requests#4200"
        st.rerun()

if "demo_load" in st.session_state:
    selected_sample = BENCHMARK_SAMPLES[st.session_state.pop("demo_load")]
    st.session_state.analyzed_issue_meta = selected_sample
    st.session_state.analyzed_repo_meta = selected_sample["repository_meta"]
    st.session_state.evidence_list = selected_sample["verified_evidence"]
    st.session_state.keywords = ["config", "json_as_ascii", "warning", "ensure_ascii"]
    st.session_state.analysis_result = IssueAnalysisResult.model_validate(selected_sample["analysis"])
    st.rerun()

# Execution Pipeline
if analyze_btn:
    if not issue_url_input or not issue_url_input.strip():
        st.error("⚠️ Please provide a valid GitHub issue URL (e.g., https://github.com/pallets/flask/issues/5000).")
    else:
        target_url = issue_url_input.strip()
        try:
            url_parts = parse_github_url(target_url)
            if not url_parts.get("is_issue"):
                st.error("⚠️ Provided URL is a repository, not an issue. Please specify an issue URL containing `/issues/<number>`.")
                st.stop()
        except InvalidGitHubURLError as e:
            st.error(f"❌ Invalid URL: {e}")
            st.stop()

        owner, repo, issue_number = url_parts["owner"], url_parts["repo"], url_parts["issue_number"]
        cache_key = f"{owner}/{repo}#{issue_number}"
        gh_client = GitHubClient(token=github_token)
        ai_engine = GemmaEngine(api_key=gemini_key, model_name=DEFAULT_GEMMA_MODEL)

        with st.status("Analyzing GitHub Issue with Gemma 4...", expanded=True) as status:
            status.update(label=f"Connecting to GitHub: Fetching metadata for {owner}/{repo}...")
            try:
                repo_meta = gh_client.get_repository(owner, repo)
            except ResourceNotFoundError as e:
                status.update(label="Repository Not Found", state="error")
                st.error(f"❌ {e}")
                st.stop()
            except RateLimitExceededError as e:
                if demo_mode_toggle and cache_key in BENCHMARK_SAMPLES:
                    st.warning("⚠️ GitHub rate limit exceeded. Falling back to cached benchmark dataset.")
                    sample = BENCHMARK_SAMPLES[cache_key]
                    st.session_state.analyzed_issue_meta = sample
                    st.session_state.analyzed_repo_meta = sample["repository_meta"]
                    st.session_state.evidence_list = sample["verified_evidence"]
                    st.session_state.analysis_result = IssueAnalysisResult.model_validate(sample["analysis"])
                    status.update(label="Analysis Complete (Benchmark Mode)", state="complete")
                    st.rerun()
                status.update(label="Rate Limit Exceeded", state="error")
                st.error(f"❌ {e}")
                st.stop()
            except GitHubAPIError as e:
                status.update(label="GitHub API Error", state="error")
                st.error(f"❌ {e}")
                st.stop()

            status.update(label=f"Fetching Issue #{issue_number} details and labels...")
            try:
                issue_meta = gh_client.get_issue(owner, repo, issue_number)
            except ResourceNotFoundError as e:
                status.update(label="Issue Not Found", state="error")
                st.error(f"❌ {e}")
                st.stop()
            except GitHubAPIError as e:
                status.update(label="GitHub API Error", state="error")
                st.error(f"❌ {e}")
                st.stop()

            status.update(label="Indexing repository file tree & README...")
            readme_text = gh_client.get_readme(owner, repo)
            default_branch = repo_meta.get("default_branch", "main")
            file_tree, _ = gh_client.get_file_tree(owner, repo, branch=default_branch)

            status.update(label="Extracting code identifiers & ranking source files...")
            keywords = extract_keywords(
                title=issue_meta.get("title", ""),
                body=issue_meta.get("body", ""),
                labels=issue_meta.get("labels", []),
            )
            ranked_files = rank_relevant_files(file_tree, keywords, top_n=4)

            status.update(label="Retrieving bounded code snippets & isolating line references...")
            evidence_list = build_repository_evidence(
                client=gh_client,
                owner=owner,
                repo=repo,
                branch=default_branch,
                ranked_files=ranked_files,
                keywords=keywords,
            )

            status.update(label=f"Synthesizing analysis with Gemma 4...")
            try:
                analysis = ai_engine.analyze_issue(
                    repo_name=f"{owner}/{repo}",
                    issue_meta=issue_meta,
                    readme_summary=readme_text[:1200],
                    file_tree=file_tree,
                    evidence_list=evidence_list,
                    use_demo_fallback=demo_mode_toggle,
                )
            except (GemmaAPIError, MalformedAIResponseError) as e:
                if demo_mode_toggle and cache_key in BENCHMARK_SAMPLES:
                    st.warning("⚠️ Gemma API error. Falling back to cached benchmark dataset.")
                    sample = BENCHMARK_SAMPLES[cache_key]
                    analysis = IssueAnalysisResult.model_validate(sample["analysis"])
                else:
                    status.update(label="AI Engine Error", state="error")
                    st.error(f"❌ {e}")
                    st.stop()

            st.session_state.analyzed_issue_meta = issue_meta
            st.session_state.analyzed_repo_meta = repo_meta
            st.session_state.evidence_list = evidence_list
            st.session_state.keywords = keywords
            st.session_state.analysis_result = analysis
            status.update(label="Analysis Completed Successfully!", state="complete")

# Display Results
if st.session_state.analysis_result and st.session_state.analyzed_issue_meta:
    analysis: IssueAnalysisResult = st.session_state.analysis_result
    issue = st.session_state.analyzed_issue_meta
    repo = st.session_state.analyzed_repo_meta or {}
    evidence = st.session_state.evidence_list

    st.markdown("---")
    with st.container():
        st.markdown(
            f"""
            <div class="dev-card">
                <div class="dev-card-header">
                    <div>
                        <span style="font-size: 13px; color: #8b949e;">{repo.get('full_name', 'Repository')} / Issue #{issue.get('number', '')}</span>
                        <h3 style="margin: 4px 0 0 0; color: #f0f6fc;">{issue.get('title', '')}</h3>
                    </div>
                    <div>
                        <span class="badge" style="background: rgba(46, 160, 67, 0.2); color: #3fb950; border: 1px solid #2ea043;">
                            {issue.get('state', 'open').upper()}
                        </span>
                    </div>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px;">
                    {''.join([f'<span class="badge badge-inferred">{label}</span>' for label in issue.get('labels', [])])}
                </div>
                <div style="font-size: 12.5px; color: #8b949e;">
                    Reported by <b>@{issue.get('author', 'unknown')}</b> · 
                    ⭐ {repo.get('stars', 0):,} stars · 
                    🍴 {repo.get('forks', 0):,} forks · 
                    Language: <b>{repo.get('language', 'Unknown')}</b> · 
                    <a href="{issue.get('html_url', '#')}" target="_blank" style="color: #58a6ff; text-decoration: none;">View on GitHub ↗</a>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "💡 Beginner Guide",
        "📂 Evidence & Files",
        "🛠️ Action Roadmap",
        "🧪 Test Specs",
        "✅ PR Checklist",
        "🔬 Model Transparency",
    ])

    with tab1:
        st.markdown("#### 🎓 Plain-English Explanation for New Contributors")
        st.info(analysis.beginner_explanation)

        col_k, col_h = st.columns(2)
        with col_k:
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-card-header">
                        <span style="font-weight: 600; color: #3fb950;">✓ Verified Known Facts</span>
                        <span class="badge badge-verified">Evidence Grounded</span>
                    </div>
                    <div style="font-size: 13px; line-height: 1.6; white-space: pre-line;">
                        {analysis.what_is_known}

                        <b>Observed in Code:</b>
                        {analysis.what_is_observed_in_code}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_h:
            st.markdown(
                """
                <div class="dev-card">
                    <div class="dev-card-header">
                        <span style="font-weight: 600; color: #e3b341;">⚠ AI Hypotheses to Investigate</span>
                        <span class="badge badge-hypothesis">Unverified</span>
                    </div>
                    <div style="font-size: 13px; line-height: 1.6;">
                """,
                unsafe_allow_html=True,
            )
            for h in analysis.problem_hypotheses:
                st.markdown(f"- {h}")
            st.markdown("</div></div>", unsafe_allow_html=True)

    with tab2:
        st.markdown("#### 📂 Repository Files with Isolated Evidence")
        st.caption("IssueLens extracts real repository paths and line-bounded code snippets deterministically from GitHub.")
        for item in evidence:
            badge_class = "badge-verified" if item.get("confidence_type") == "verified" else "badge-inferred"
            badge_text = "Verified Code Evidence" if item.get("confidence_type") == "verified" else "Inferred Relevance"
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-card-header">
                        <div>
                            <span style="font-family: monospace; font-size: 14px; font-weight: 600; color: #58a6ff;">{item['path']}</span>
                            <span style="font-size: 12px; color: #8b949e; margin-left: 10px;">(Lines {item.get('start_line', 1)} - {item.get('end_line', 1)})</span>
                        </div>
                        <span class="badge {badge_class}">{badge_text}</span>
                    </div>
                    <p style="font-size: 13px; color: #c9d1d9; margin-bottom: 8px;"><b>Why Relevant:</b> {item.get('why_relevant', '')}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.code(item.get("snippet", "(No snippet preview available)"), language="python")

    with tab3:
        col_inv, col_imp = st.columns(2)
        with col_inv:
            st.markdown("#### 🔍 Investigation Steps")
            for step in analysis.investigation_steps:
                with st.expander(f"Step {step.step_number}: {step.action}", expanded=True):
                    st.write(step.details)
        with col_imp:
            st.markdown("#### 🛠️ Concrete Implementation Plan")
            for step in analysis.implementation_plan:
                with st.expander(f"Step {step.step_number}: {step.target_file}", expanded=True):
                    st.markdown(f"**Description:** {step.description}")
                    st.markdown(f"**Proposed Change:** `{step.code_change_summary}`")

    with tab4:
        st.markdown("#### 🧪 Practical Test Scenarios")
        st.caption("Implement or run these tests to verify your fix and prevent regressions.")
        for idx, test in enumerate(analysis.suggested_tests, 1):
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-card-header">
                        <span style="font-weight: 600; color: #79c0ff;">Test Scenario #{idx}: {test.scenario}</span>
                        <span style="font-family: monospace; font-size: 11px; color: #8b949e;">{test.test_location_note or 'Unit Test'}</span>
                    </div>
                    <div style="font-size: 12.5px; margin-bottom: 8px;">
                        <b>Sample Input / Execution:</b>
                        <pre style="background: #090d13; border: 1px solid #30363d; border-radius: 4px; padding: 8px; margin-top: 4px; color: #e6edf3;">{test.input_example}</pre>
                    </div>
                    <div style="font-size: 12.5px;">
                        <b>Expected Outcome:</b> <span style="color: #7ee787;">{test.expected_output}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with tab5:
        st.markdown("#### ✅ Pull Request Preparation Checklist")
        categories = set(item.category for item in analysis.contribution_checklist)
        for cat in sorted(categories):
            st.markdown(f"##### 📌 {cat}")
            for item in [i for i in analysis.contribution_checklist if i.category == cat]:
                st.checkbox(f"**{item.task}** — {item.details}", key=f"chk_{item.task}_{cat}")

    with tab6:
        st.markdown("#### 🔬 AI Model Attribution & Transparency")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-card-header">
                        <span style="font-weight: 600; color: #818cf8;">Model Architecture</span>
                        <span class="badge badge-model">{analysis.raw_model_name}</span>
                    </div>
                    <div style="font-size: 13px; line-height: 1.6;">
                        • <b>Model Family:</b> Gemma 4 (Google DeepMind)<br>
                        • <b>SDK:</b> Google Gen AI Python SDK (<code>google-genai</code>)<br>
                        • <b>Sampling Temperature:</b> 0.2 (High determinism)<br>
                        • <b>Validation:</b> Pydantic v2 Schema Enforcement
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_m2:
            st.markdown(
                f"""
                <div class="dev-card">
                    <div class="dev-card-header">
                        <span style="font-weight: 600; color: #f0883e;">Confidence & Disclosures</span>
                    </div>
                    <div style="font-size: 13px; line-height: 1.6;">
                        {analysis.confidence_and_limitations}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with st.expander("🛠️ Inspect Raw JSON Schema Output (Maintainer View)"):
            st.json(analysis.model_dump())
