"""Repository Analyzer Module for IssueLens.

Performs deterministic, evidence-based keyword extraction and file discovery:
- Tokenizes issue title, body, and labels to extract high-value code identifiers.
- Filters and scores repository file paths against extracted keywords.
- Extracts bounded code snippets with exact line references (#L...-L...).
- Strictly distinguishes verified code evidence from inferred structural relevance.
- Never fabricates repository files, functions, or line numbers.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple


# Ignore non-code, metadata, and auto-generated paths
IGNORED_PATH_PATTERNS = [
    r"node_modules/",
    r"\.git/",
    r"\.github/",
    r"vendor/",
    r"dist/",
    r"build/",
    r"\.next/",
    r"__pycache__/",
    r"\.pytest_cache/",
    r"\.venv/",
    r"venv/",
    r"env/",
    r"package-lock\.json$",
    r"yarn\.lock$",
    r"pnpm-lock\.yaml$",
    r"poetry\.lock$",
    r"Gemfile\.lock$",
    r"cargo\.lock$",
    r"\.min\.(js|css)$",
    r"\.(png|jpg|jpeg|gif|svg|ico|webp|woff|woff2|ttf|eot|mp4|webm|zip|tar|gz|pdf|ai|psd|eps)$",
]

# Stop words to ignore during issue keyword extraction
COMMON_STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "cannot", "could", "did", "do", "does", "doing", "down", "during", "each", "few",
    "for", "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of",
    "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "we", "were", "what",
    "when", "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your",
    "yours", "yourself", "yourselves",
    # Generic issue words
    "issue", "bug", "problem", "error", "fix", "please", "help", "thanks", "reproduce", "repro",
    "expected", "actual", "behavior", "steps", "version", "using", "tried", "getting", "failed",
    "github", "repo", "repository", "feature", "request", "support", "added", "update", "run",
    "running", "code", "file", "line", "test", "tests",
}

# Source code file extensions prioritized for analysis
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".cs", ".swift", ".kt", ".scala", ".sh", ".bash", ".yaml", ".yml", ".json",
    ".toml", ".sql", ".html", ".css",
}


def extract_keywords(title: str, body: str, labels: Optional[List[str]] = None) -> List[str]:
    """Extract code identifiers, file mentions, and significant keywords from issue text.

    Returns ranked list of unique lowercase keywords.
    """
    text = f"{title}\n{body}\n{' '.join(labels or [])}"

    # Extract backtick-quoted code identifiers (high value)
    code_mentions = re.findall(r"`([^`\n]+)`", text)

    # Extract words, camelCase, and snake_case tokens
    raw_tokens = re.findall(r"[A-Za-z0-9_\.\-]+", text)

    keywords: List[str] = []
    seen: Set[str] = set()

    def add_keyword(token: str, boost: bool = False):
        t = token.strip(".-_").lower()
        if len(t) >= 3 and t not in COMMON_STOP_WORDS and not t.isdigit():
            if t not in seen:
                seen.add(t)
                keywords.append(t)

    # 1. Backtick mentions first
    for mention in code_mentions:
        for subtoken in re.split(r"[\s\(\)\[\]\{\}\<\>,;:]+", mention):
            add_keyword(subtoken, boost=True)

    # 2. File mentions like 'foo.py', 'bar.ts', 'src/auth.js'
    for match in re.findall(r"\b[\w\.\-/]+\.(?:py|js|ts|tsx|jsx|go|rs|java|cpp|c|rb|json|yaml|yml)\b", text, re.IGNORECASE):
        add_keyword(match, boost=True)
        # Also add basename
        basename = os.path.basename(match)
        name, _ = os.path.splitext(basename)
        add_keyword(name, boost=True)

    # 3. CamelCase and snake_case tokens
    for token in raw_tokens:
        if "_" in token or any(c.isupper() for c in token[1:]):
            add_keyword(token, boost=True)
        add_keyword(token)

    return keywords[:30]


def is_ignored_path(path: str) -> bool:
    """Check if file path belongs to ignored build/cache/vendor directories."""
    norm_path = path.replace("\\", "/")
    for pattern in IGNORED_PATH_PATTERNS:
        if re.search(pattern, norm_path, re.IGNORECASE):
            return True
    return False


def score_file_path(path: str, keywords: List[str]) -> Tuple[float, List[str]]:
    """Score relevance of a file path based on matching keywords.

    Returns:
        Tuple[float, List[str]]: (score, matched_keywords)
    """
    if is_ignored_path(path):
        return 0.0, []

    path_lower = path.lower().replace("\\", "/")
    basename = os.path.basename(path_lower)
    name_without_ext, ext = os.path.splitext(basename)

    # Check extension relevance
    ext_weight = 1.0 if ext in CODE_EXTENSIONS else 0.4
    if basename in ("readme.md", "license", "setup.py", "pyproject.toml", "package.json"):
        ext_weight = 0.5  # useful metadata, but not primary source

    score = 0.0
    matched = []

    for rank, kw in enumerate(keywords):
        weight = 1.0 / (1.0 + 0.1 * rank)  # Earlier keywords have higher weight

        if kw == name_without_ext:
            # Exact filename match
            score += 5.0 * weight
            matched.append(kw)
        elif kw in name_without_ext:
            # Substring in filename
            score += 3.0 * weight
            matched.append(kw)
        elif kw in path_lower:
            # Keyword in directory hierarchy
            score += 1.5 * weight
            matched.append(kw)

    return score * ext_weight, matched


def rank_relevant_files(file_tree: List[str], keywords: List[str], top_n: int = 5) -> List[Dict[str, Any]]:
    """Find top relevant files in file tree matching issue keywords."""
    scored_files: List[Dict[str, Any]] = []

    for path in file_tree:
        score, matched = score_file_path(path, keywords)
        if score > 0:
            scored_files.append({
                "path": path,
                "score": round(score, 2),
                "matched_keywords": matched,
            })

    scored_files.sort(key=lambda x: x["score"], reverse=True)

    # If no files matched keywords, pick key entrypoints if present
    if not scored_files and file_tree:
        fallback_candidates = [
            f for f in file_tree
            if not is_ignored_path(f) and os.path.splitext(f)[1] in CODE_EXTENSIONS
        ]
        # Look for common entrypoints
        for candidate in fallback_candidates[:top_n]:
            scored_files.append({
                "path": candidate,
                "score": 0.5,
                "matched_keywords": ["entrypoint-candidate"],
            })

    return scored_files[:top_n]


def extract_evidence_snippets(
    file_content: str,
    keywords: List[str],
    max_snippets: int = 2,
    window_lines: int = 6,
) -> List[Dict[str, Any]]:
    """Extract bounded code snippet windows with exact line numbers matching keywords.

    Returns:
        List of dicts: {
            "start_line": int,
            "end_line": int,
            "snippet": str,
            "matched_keywords": List[str],
            "confidence_type": "verified" | "inferred"
        }
    """
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
            # Score line by matched keyword count and length
            score = sum(len(kw) for kw in matched)
            line_scores.append((idx + 1, score, matched))

    snippets: List[Dict[str, Any]] = []
    used_line_ranges: List[Tuple[int, int]] = []

    # Sort lines by matching score
    line_scores.sort(key=lambda x: x[1], reverse=True)

    for line_num, _, matched_kws in line_scores:
        if len(snippets) >= max_snippets:
            break

        start = max(1, line_num - window_lines)
        end = min(total_lines, line_num + window_lines)

        # Avoid overlapping snippet windows
        overlap = any(not (end < r_start or start > r_end) for r_start, r_end in used_line_ranges)
        if overlap:
            continue

        used_line_ranges.append((start, end))

        # Format snippet with line numbers
        snippet_lines = [
            f"{i:4d} | {lines[i - 1]}"
            for i in range(start, end + 1)
        ]
        snippet_text = "\n".join(snippet_lines)

        snippets.append({
            "start_line": start,
            "end_line": end,
            "snippet": snippet_text,
            "matched_keywords": matched_kws,
            "confidence_type": "verified",
        })

    # If no lines matched keywords directly, return the head of the file (first 15 lines) as inferred
    if not snippets and total_lines > 0:
        end = min(total_lines, 15)
        snippet_lines = [f"{i:4d} | {lines[i - 1]}" for i in range(1, end + 1)]
        snippets.append({
            "start_line": 1,
            "end_line": end,
            "snippet": "\n".join(snippet_lines),
            "matched_keywords": [],
            "confidence_type": "inferred",
        })

    return snippets


def build_repository_evidence(
    client: Any,
    owner: str,
    repo: str,
    branch: str,
    ranked_files: List[Dict[str, Any]],
    keywords: List[str],
) -> List[Dict[str, Any]]:
    """Fetch file contents and compile verified evidence for top ranked files."""
    evidence_list: List[Dict[str, Any]] = []

    for file_info in ranked_files:
        path = file_info["path"]
        content = client.get_file_content(owner, repo, path, branch=branch)

        if content is None:
            # Handle missing, unreadable, or binary files gracefully
            matched_kws = file_info.get("matched_keywords", [])
            evidence_list.append({
                "path": path,
                "score": file_info.get("score", 0.0),
                "matched_keywords": matched_kws,
                "has_content": False,
                "total_lines": 0,
                "start_line": 1,
                "end_line": 1,
                "snippet": "(Source content unavailable: binary, exceeded 60KB limit, or not found on branch)",
                "code_snippet": "(Source content unavailable: binary, exceeded 60KB limit, or not found on branch)",
                "confidence_type": "inferred",
                "relationship": "INFERRED",
                "why_relevant": (
                    f"Path matched issue keywords ({', '.join(matched_kws)}), but file content was not retrievable."
                    if matched_kws else "Structural candidate; content not retrievable."
                ),
                "why_related": (
                    f"Path matched issue keywords ({', '.join(matched_kws)}), but file content was not retrievable."
                    if matched_kws else "Structural candidate; content not retrievable."
                ),
            })
            continue

        snippets = extract_evidence_snippets(content, keywords)
        primary_snippet = snippets[0] if snippets else None

        conf_type = primary_snippet["confidence_type"] if primary_snippet else "inferred"
        rel_type = "VERIFIED" if conf_type == "verified" else "INFERRED"
        snip_text = primary_snippet["snippet"] if primary_snippet else "(No text preview available)"

        why_text = (
            f"Matches issue keywords: {', '.join(file_info.get('matched_keywords', []))}"
            if file_info.get("matched_keywords")
            else "Structural entrypoint candidate"
        )

        evidence_list.append({
            "path": path,
            "score": file_info.get("score", 0.0),
            "matched_keywords": file_info.get("matched_keywords", []),
            "has_content": True,
            "total_lines": len(content.splitlines()),
            "start_line": primary_snippet["start_line"] if primary_snippet else 1,
            "end_line": primary_snippet["end_line"] if primary_snippet else 1,
            "snippet": snip_text,
            "code_snippet": snip_text,
            "confidence_type": conf_type,
            "relationship": rel_type,
            "why_relevant": why_text,
            "why_related": why_text,
        })

    return evidence_list


from github_client import FileSnippet


class RepositoryAnalyzer:
    """Keyword-based repository analyzer for grounding issue context."""

    def __init__(self, max_file_candidates: int = 4, max_snippet_lines: int = 80):
        self.max_file_candidates = max_file_candidates
        self.max_snippet_lines = max_snippet_lines

    def extract_keywords_and_mentions(
        self,
        title: str,
        body: str,
        labels: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Extract high-value keywords and explicitly cited files."""
        keywords = extract_keywords(title, body, labels)
        combined_text = f"{title}\n{body}\n{' '.join(labels)}"
        file_pattern = r"(?:`|[\s\"'])((?:[a-zA-Z0-9_\-\.\/]+)\.[a-zA-Z0-9]{1,5})(?:`|[\s\"'\:\,\)])"
        raw_file_matches = re.findall(file_pattern, combined_text)
        mentioned_files: List[str] = []
        for match in raw_file_matches:
            clean = match.strip().lstrip("./")
            if not clean.startswith(("http://", "https://", "www.")) and ("/" in clean or "." in clean):
                ext = os.path.splitext(clean)[1].lower()
                if ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".json", ".yaml", ".yml", ".toml", ".md", ".sh"}:
                    if clean not in mentioned_files:
                        mentioned_files.append(clean)
        return keywords, mentioned_files

    def rank_candidate_files(
        self,
        file_tree: List[str],
        keywords: List[str],
        mentioned_files: Optional[List[str]] = None
    ) -> List[Tuple[str, float, str]]:
        """Rank repository files against issue keywords."""
        ranked_dicts = rank_relevant_files(file_tree, keywords, top_n=self.max_file_candidates)
        results = []
        for d in ranked_dicts:
            reason = f"Matched issue keywords: {', '.join(d.get('matched_keywords', []))}" if d.get('matched_keywords') else "Structural relevance"
            results.append((d["path"], d["score"], reason))
        return results

    def extract_snippet_from_content(
        self,
        path: str,
        content: str,
        keywords: List[str],
        evidence_reason: str
    ) -> FileSnippet:
        """Extract line-numbered snippet matching keywords."""
        lines = content.splitlines()
        total_lines = len(lines)
        snippets = extract_evidence_snippets(content, keywords, max_snippets=1, window_lines=self.max_snippet_lines // 2)
        if snippets:
            s = snippets[0]
            return FileSnippet(
                path=path,
                content=s["snippet"],
                start_line=s["start_line"],
                end_line=s["end_line"],
                total_lines=total_lines,
                is_truncated=total_lines > (s["end_line"] - s["start_line"] + 1),
                evidence_reason=evidence_reason
            )
        end = min(total_lines, 20)
        preview = "\n".join(f"{i:4d} | {lines[i - 1]}" for i in range(1, end + 1))
        return FileSnippet(
            path=path,
            content=preview,
            start_line=1,
            end_line=end,
            total_lines=total_lines,
            is_truncated=total_lines > end,
            evidence_reason=evidence_reason
        )

    def retrieve_evidence(
        self,
        client: Any,
        owner: str,
        repo: str,
        file_tree: List[str],
        keywords: List[str],
        mentioned_files: Optional[List[str]] = None,
        default_branch: str = "main"
    ) -> List[FileSnippet]:
        """Retrieve evidence snippets for top candidate files."""
        ranked = self.rank_candidate_files(file_tree, keywords, mentioned_files)
        file_snippets: List[FileSnippet] = []
        for path, score, reason in ranked:
            content = client.fetch_file_content(owner, repo, path, ref=default_branch)
            if content is not None:
                snippet = self.extract_snippet_from_content(path, content, keywords, reason)
                file_snippets.append(snippet)
        return file_snippets

