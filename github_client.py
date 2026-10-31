"""GitHub Client Module for IssueLens.

Provides robust, evidence-focused access to the GitHub REST API:
- URL parsing and validation (repos and issues)
- Issue metadata retrieval
- Repository README and recursive file tree indexing
- Bounded source file content fetching
- Comprehensive error handling (404, 403, 429, timeouts, malformed URLs)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import requests


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class GitHubRateLimit:
    """Tracks GitHub API rate limit state."""
    limit: int = 60
    remaining: int = 60
    reset_timestamp: int = 0

    @property
    def reset_datetime(self) -> Optional[datetime]:
        if self.reset_timestamp:
            return datetime.fromtimestamp(self.reset_timestamp, tz=timezone.utc)
        return None

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class RepoMetadata:
    """Repository metadata."""
    owner: str
    name: str
    full_name: str
    description: str
    default_branch: str
    language: Optional[str]
    stars: int
    forks: int
    open_issues: int
    html_url: str

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class IssueData:
    """GitHub issue details."""
    owner: str
    repo: str
    number: int
    title: str
    body: str
    state: str
    html_url: str
    author: str
    created_at: str
    updated_at: str = ""
    labels: List[str] = field(default_factory=list)
    comments_count: int = 0
    top_comments: List[str] = field(default_factory=list)
    is_pull_request: bool = False

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


# Compatibility aliases
GitHubRepoInfo = RepoMetadata
GitHubIssue = IssueData


@dataclass
class FileSnippet:
    """Retrieved source code snippet with exact line numbers."""
    path: str
    content: str
    start_line: int
    end_line: int
    total_lines: int
    is_truncated: bool = False
    evidence_reason: str = ""

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, reset_time: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code
        self.reset_time = reset_time


class RateLimitExceededError(GitHubAPIError):
    """Raised when GitHub API rate limit (403/429) is reached."""
    pass


GitHubRateLimitError = RateLimitExceededError


class ResourceNotFoundError(GitHubAPIError):
    """Raised when repository or issue is not found (404)."""
    pass


GitHubResourceNotFoundError = ResourceNotFoundError


class InvalidGitHubURLError(ValueError):
    """Raised when a provided URL cannot be parsed into GitHub components."""
    pass


class GitHubNetworkError(GitHubAPIError):
    """Raised on connection timeout or network failure."""
    pass


# ---------------------------------------------------------------------------
# URL Parsing Helper
# ---------------------------------------------------------------------------

def parse_github_url(url: str) -> Dict[str, Any]:
    """Parse a GitHub repository or issue URL."""
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


# ---------------------------------------------------------------------------
# GitHub Client
# ---------------------------------------------------------------------------

class GitHubClient:
    """Production-grade client for the public GitHub REST API."""

    BASE_URL = "https://api.github.com"
    RAW_BASE_URL = "https://raw.githubusercontent.com"
    MAX_FILE_BYTES = 60_000  # ~60 KB bound to prevent memory exhaustion

    EXCLUDED_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
        ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo",
        ".whl", ".ttf", ".woff", ".woff2", ".eot",
        ".mp4", ".mov", ".avi", ".mp3", ".wav",
        ".ai", ".psd", ".eps", ".sketch",
        ".lock", ".map", ".min.js", ".min.css"
    }

    def __init__(self, token: Optional[str] = None, timeout: int = 15):
        raw_token = token or os.environ.get("GITHUB_TOKEN")
        self.token = raw_token.strip() if raw_token and raw_token.strip() else None
        self.timeout = timeout
        self.session = requests.Session()
        self.rate_limit = GitHubRateLimit()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "IssueLens-Assistant/1.0",
        })
        if self.token:
            self.session.headers["Authorization"] = f"token {self.token}"

    @staticmethod
    def parse_repo_url(url: str) -> Tuple[str, str]:
        """Extract (owner, repo) from a GitHub repository URL."""
        parsed = parse_github_url(url)
        return parsed["owner"], parsed["repo"]

    @staticmethod
    def parse_issue_url(url: str) -> Tuple[str, str, int]:
        """Extract (owner, repo, issue_number) from a GitHub issue URL."""
        parsed = parse_github_url(url)
        if not parsed.get("is_issue") or parsed.get("issue_number") is None:
            raise ValueError(f"URL is not a valid GitHub issue URL: '{url}'")
        return parsed["owner"], parsed["repo"], parsed["issue_number"]

    def _update_rate_limit(self, resp: requests.Response) -> None:
        try:
            limit = resp.headers.get("X-RateLimit-Limit")
            remaining = resp.headers.get("X-RateLimit-Remaining")
            reset = resp.headers.get("X-RateLimit-Reset")
            if limit is not None:
                self.rate_limit.limit = int(limit)
            if remaining is not None:
                self.rate_limit.remaining = int(remaining)
            if reset is not None:
                self.rate_limit.reset_timestamp = int(reset)
        except (ValueError, TypeError):
            pass

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        url = endpoint if endpoint.startswith("http") else f"{self.BASE_URL}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        try:
            resp = self.session.request(method, url, **kwargs)
        except requests.exceptions.Timeout as exc:
            raise GitHubNetworkError(f"Request to GitHub timed out after {self.timeout}s: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise GitHubNetworkError(f"Failed to connect to GitHub: {exc}") from exc
        except requests.exceptions.RequestException as exc:
            raise GitHubNetworkError(f"Network error communicating with GitHub: {exc}") from exc

        self._update_rate_limit(resp)

        if resp.status_code in (403, 429):
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            reset_time = int(reset_ts) if reset_ts and reset_ts.isdigit() else None
            msg = (
                f"GitHub API rate limit exceeded ({resp.status_code}). "
                "Add a personal GITHUB_TOKEN to increase quota to 5,000 requests/hour."
            )
            raise RateLimitExceededError(msg, status_code=resp.status_code, reset_time=reset_time)

        if resp.status_code == 404:
            raise ResourceNotFoundError(
                f"Requested resource not found on GitHub (404): {url}. "
                "Ensure repository is public and spelled correctly.",
                status_code=404
            )

        if not resp.ok:
            try:
                err_data = resp.json()
                api_msg = err_data.get("message", resp.text)
            except Exception:
                api_msg = resp.text
            raise GitHubAPIError(f"GitHub API error {resp.status_code}: {api_msg}", status_code=resp.status_code)

        return resp

    def fetch_repo_metadata(self, owner: str, repo: str) -> RepoMetadata:
        """Fetch repository metadata and default branch."""
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}")
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Repository '{owner}/{repo}' was not found. Please verify the URL and confirm the repository is public.",
                status_code=404,
            )
        data = resp.json()
        return RepoMetadata(
            owner=owner,
            name=data.get("name", repo),
            full_name=data.get("full_name", f"{owner}/{repo}"),
            description=data.get("description") or "No description provided.",
            default_branch=data.get("default_branch", "main"),
            language=data.get("language") or "Unspecified",
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            open_issues=data.get("open_issues_count", 0),
            html_url=data.get("html_url", f"https://github.com/{owner}/{repo}"),
        )

    get_repository = fetch_repo_metadata

    def fetch_issue(self, owner: str, repo: str, issue_number: int) -> IssueData:
        """Fetch issue title, description, labels, and top comments."""
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/issues/{issue_number}")
        except ResourceNotFoundError:
            raise ResourceNotFoundError(
                f"Issue #{issue_number} was not found in repository '{owner}/{repo}'. Please check the issue number.",
                status_code=404,
            )
        data = resp.json()

        labels = [l.get("name", "") for l in data.get("labels", []) if isinstance(l, dict)]
        comments_count = data.get("comments", 0)
        top_comments: List[str] = []

        if comments_count > 0:
            try:
                c_resp = self._request(
                    "GET",
                    f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                    params={"per_page": 3}
                )
                for c in c_resp.json():
                    b = (c.get("body") or "").strip()
                    if b:
                        top_comments.append(b[:800])
            except Exception:
                top_comments = []

        return IssueData(
            owner=owner,
            repo=repo,
            number=issue_number,
            title=data.get("title", f"Issue #{issue_number}"),
            body=data.get("body") or "",
            state=data.get("state", "open"),
            html_url=data.get("html_url", f"https://github.com/{owner}/{repo}/issues/{issue_number}"),
            author=(data.get("user") or {}).get("login", "unknown"),
            created_at=data.get("created_at", ""),
            labels=labels,
            comments_count=comments_count,
            top_comments=top_comments,
            is_pull_request="pull_request" in data,
        )

    get_issue = fetch_issue

    def fetch_readme(self, owner: str, repo: str, max_chars: int = 8000) -> str:
        """Fetch repository README content. Returns empty string if missing."""
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/readme")
            data = resp.json()
            raw_content = data.get("content", "")
            if raw_content:
                decoded = base64.b64decode(raw_content).decode("utf-8", errors="replace")
                return decoded[:max_chars]
            return ""
        except ResourceNotFoundError:
            return ""
        except Exception:
            return ""

    get_readme = fetch_readme

    def fetch_file_tree(
        self,
        owner: str,
        repo: str,
        default_branch: str = "main",
        branch: Optional[str] = None,
        max_items: int = 4000,
    ) -> List[str]:
        """Fetch recursive file tree using the Git Trees API."""
        target_branch = branch or default_branch or "main"
        try:
            resp = self._request("GET", f"/repos/{owner}/{repo}/git/trees/{target_branch}?recursive=1")
            data = resp.json()
            tree = data.get("tree", [])

            file_paths: List[str] = []
            for item in tree:
                if item.get("type") == "blob" and "path" in item:
                    p = item["path"]
                    lower_p = p.lower()
                    if (
                        lower_p.startswith((".git/", ".github/workflows/", "node_modules/", "dist/", "build/"))
                        or "/node_modules/" in lower_p
                        or "/site-packages/" in lower_p
                    ):
                        continue
                    _, ext = os.path.splitext(lower_p)
                    if ext in self.EXCLUDED_EXTENSIONS:
                        continue
                    file_paths.append(p)

            return file_paths[:max_items]
        except ResourceNotFoundError:
            if default_branch == "main":
                try:
                    return self.fetch_file_tree(owner, repo, default_branch="master", max_items=max_items)
                except Exception:
                    pass
            return []
        except Exception:
            return []

    get_file_tree = fetch_file_tree

    def fetch_file_content(
        self, owner: str, repo: str, path: str, ref: Optional[str] = None, branch: Optional[str] = None
    ) -> Optional[str]:
        """Fetch file content bounded by MAX_FILE_BYTES."""
        target_branch = branch or ref or "main"
        raw_url = f"{self.RAW_BASE_URL}/{owner}/{repo}/{target_branch}/{path}"
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
            params = {"ref": target_branch} if target_branch else {}
            resp = self._request("GET", f"/repos/{owner}/{repo}/contents/{path}", params=params)
            data = resp.json()
            if data.get("type") != "file":
                return None
            size = data.get("size", 0)
            if size > self.MAX_FILE_BYTES:
                return None
            content_b64 = data.get("content", "")
            if content_b64:
                return base64.b64decode(content_b64).decode("utf-8", errors="replace")
        except Exception:
            return None

        return None

    get_file_content = fetch_file_content

    def get_rate_limit_status(self) -> Dict[str, Any]:
        """Fetch current rate limit status from GitHub REST API."""
        try:
            resp = self._request("GET", "/rate_limit")
            data = resp.json()
            core = data.get("resources", {}).get("core", {})
            remaining = core.get("remaining", self.rate_limit.remaining)
            limit = core.get("limit", self.rate_limit.limit)
            reset_ts = core.get("reset", self.rate_limit.reset_timestamp)
            reset_dt = (
                datetime.fromtimestamp(reset_ts, tz=timezone.utc).strftime("%H:%M:%S UTC")
                if reset_ts
                else "Unknown"
            )
            return {
                "limit": limit,
                "remaining": remaining,
                "reset_time": reset_dt,
                "authenticated": bool(self.token),
            }
        except Exception:
            return {
                "limit": getattr(self.rate_limit, "limit", 60),
                "remaining": getattr(self.rate_limit, "remaining", 60),
                "reset_time": "Unknown",
                "authenticated": bool(self.token),
            }

