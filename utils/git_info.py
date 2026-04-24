"""Best-effort commit metadata for the help-overview page.

Two sources, in priority order:

1. Local ``git`` — fast, used on the author's workstation and any
   deployment that bundles a clone of the repo.
2. GitHub REST API — used when the repo isn't on disk (e.g. cloud
   deployments). Requires an auth token for private repos.

Both paths accept a list of pathspecs so callers can scope the query
(include/exclude specific files). All functions return ``{}`` on any
failure so callers can transparently fall back to hardcoded values.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path


# ---------------------------------------------------------------------------
# Local git
# ---------------------------------------------------------------------------

def _run(repo: Path, args: list[str]) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def git_stats(repo: str, pathspecs: tuple[str, ...] | None = None) -> dict:
    """Return first_commit, latest_commit, count, last_subject, last_hash.

    ``pathspecs`` is a tuple of git pathspec strings — supports
    ``:(exclude,glob)`` forms. Returns ``{}`` if the repo isn't a
    git working tree.
    """
    p = Path(repo).expanduser()
    if _run(p, ["rev-parse", "--is-inside-work-tree"]) != "true":
        return {}

    trail = ["--", *pathspecs] if pathspecs else []

    dates = _run(p, ["log", "--format=%ad", "--date=short", *trail])
    if not dates:
        return {}
    lines = [ln for ln in dates.splitlines() if ln]
    if not lines:
        return {}

    count_out = _run(p, ["rev-list", "--count", "HEAD", *trail])
    try:
        count = int(count_out) if count_out else len(lines)
    except ValueError:
        count = len(lines)

    last_subject = _run(p, ["log", "-1", "--format=%s", *trail]) or ""
    last_hash = _run(p, ["log", "-1", "--format=%h", *trail]) or ""

    return {
        "first_commit": lines[-1],
        "latest_commit": lines[0],
        "count": count,
        "last_subject": last_subject,
        "last_hash": last_hash,
    }


# ---------------------------------------------------------------------------
# GitHub REST API fallback
# ---------------------------------------------------------------------------

_GH_API = "https://api.github.com"


def _gh_get(url: str, token: str | None) -> tuple[list | dict | None, dict]:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "radiantcare-dashboard")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data, dict(resp.headers)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError, OSError):
        return None, {}


def _fetch_path_commits(owner: str, repo: str, path: str, token: str | None) -> list[dict]:
    """Return all commits that touched ``path`` (paginated). Empty ``path``
    lists all commits in the repo."""
    commits: list[dict] = []
    page = 1
    while True:
        qs = f"per_page=100&page={page}"
        if path:
            qs = f"path={urllib.parse.quote(path)}&{qs}"
        url = f"{_GH_API}/repos/{owner}/{repo}/commits?{qs}"
        data, _headers = _gh_get(url, token)
        if not isinstance(data, list) or not data:
            break
        commits.extend(data)
        if len(data) < 100:
            break
        page += 1
        if page > 20:  # safety cap — 2000 commits per file is plenty
            break
    return commits


def github_list_tree(owner: str, repo: str, token: str | None, branch: str = "HEAD") -> list[str]:
    """List every blob path in the repo via the git/trees recursive endpoint."""
    url = f"{_GH_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    data, _ = _gh_get(url, token)
    if not isinstance(data, dict):
        return []
    return [e.get("path", "") for e in data.get("tree", []) if e.get("type") == "blob"]


def github_stats(owner: str, repo: str, paths: tuple[str, ...], token: str | None) -> dict:
    """Aggregate commit metadata across a list of repo-relative paths.

    Dedupes by commit sha (a single commit can touch many files).
    """
    if not paths:
        return {}

    with ThreadPoolExecutor(max_workers=min(8, len(paths))) as pool:
        per_file = list(pool.map(
            lambda pth: _fetch_path_commits(owner, repo, pth, token),
            paths,
        ))

    seen: dict[str, dict] = {}
    for commits in per_file:
        for c in commits:
            sha = c.get("sha")
            if not sha or sha in seen:
                continue
            seen[sha] = c
    if not seen:
        return {}

    def _iso_date(c: dict) -> str:
        author = (c.get("commit") or {}).get("author") or {}
        ts = author.get("date") or ""
        return ts[:10]

    sorted_commits = sorted(seen.values(), key=_iso_date)
    first = _iso_date(sorted_commits[0])
    last_commit = sorted_commits[-1]
    latest = _iso_date(last_commit)
    subject = ((last_commit.get("commit") or {}).get("message") or "").splitlines()[0] if last_commit else ""
    sha_short = (last_commit.get("sha") or "")[:7]

    return {
        "first_commit": first,
        "latest_commit": latest,
        "count": len(seen),
        "last_subject": subject,
        "last_hash": sha_short,
    }


# ---------------------------------------------------------------------------
# Public: try local git first, then GitHub API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def repo_stats(
    local_repo: str | None,
    local_pathspecs: tuple[str, ...] | None,
    gh_owner: str | None,
    gh_repo: str | None,
    gh_paths: tuple[str, ...] | None,
    gh_token_env: tuple[str, ...] = ("ARIA_GH_TOKEN", "GITHUB_TOKEN"),
) -> dict:
    if local_repo:
        stats = git_stats(local_repo, local_pathspecs)
        if stats:
            return stats
    if gh_owner and gh_repo and gh_paths:
        token = None
        for var in gh_token_env:
            token = os.environ.get(var)
            if token:
                break
        stats = github_stats(gh_owner, gh_repo, gh_paths, token)
        if stats:
            return stats
    return {}


def span_months(first_iso: str, last_iso: str) -> float | None:
    from datetime import date
    try:
        a = date.fromisoformat(first_iso)
        b = date.fromisoformat(last_iso)
    except ValueError:
        return None
    return max((b - a).days / 30.44, 0.0)
