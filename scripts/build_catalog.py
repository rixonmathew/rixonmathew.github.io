"""Build the project catalog (data/repos.json) from every repo owned by OWNER.

Summaries are cached in data/catalog.json, keyed by repo name, and are only
regenerated when a repo is new or its README changes. A Claude summary is also
written back as the repo's GitHub description, unless someone wrote that
description by hand.

Env:
  GH_TOKEN            token that can read OWNER's private repos (and edit their
                      descriptions, for write-back)
  ANTHROPIC_API_KEY   optional; without it, new or changed repos keep their
                      GitHub description and no summary is generated
  OWNER               defaults to rixonmathew
  WRITE_DESCRIPTIONS  "1" (default) to PATCH descriptions on GitHub, "0" to only report
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OWNER = os.environ.get("OWNER", "rixonmathew")
TOKEN = os.environ["GH_TOKEN"]
WRITE = os.environ.get("WRITE_DESCRIPTIONS", "1") == "1"
ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "catalog.json"
OUT = ROOT / "data" / "repos.json"
CATALOG_REPO = f"{OWNER}.github.io"

CATEGORIES = ["AI & agents", "Data platforms", "Infra & ops", "Apps", "Sites & writing", "Learning", "Other"]
MODEL = "claude-opus-5-5"
DESC_MAX = 350  # GitHub's limit on repo descriptions


def gh(path: str, method: str = "GET", body: dict | None = None):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r), r.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        if e.code in (404, 409):  # no README / empty repo
            return None, ""
        raise


def list_repos() -> list[dict]:
    repos, url = [], "/user/repos?affiliation=owner&per_page=100&sort=pushed"
    while url:
        page, link = gh(url)
        repos += page
        url = next((p.split(";")[0].strip("<> ") for p in link.split(",") if 'rel="next"' in p), None)
    return [r for r in repos if r["owner"]["login"] == OWNER and r["name"] != CATALOG_REPO]


def readme(name: str) -> tuple[str | None, str]:
    data, _ = gh(f"/repos/{OWNER}/{name}/readme")
    if not data:
        return None, ""
    return data["sha"], base64.b64decode(data["content"]).decode("utf-8", "ignore")


def root_files(name: str) -> list[str]:
    data, _ = gh(f"/repos/{OWNER}/{name}/contents/")
    return [f["name"] for f in data or []][:40]


def last_commit(name: str) -> dict | None:
    data, _ = gh(f"/repos/{OWNER}/{name}/commits?per_page=1")
    if not data:
        return None
    c = data[0]["commit"]
    return {"message": c["message"].splitlines()[0][:140], "date": c["committer"]["date"]}


SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One sentence, at most 160 characters, saying what the repo is for."},
        "category": {"type": "string", "enum": CATEGORIES},
    },
    "required": ["summary", "category"],
    "additionalProperties": False,
}

PROMPT = """You are cataloguing a developer's personal GitHub repos so they can remember what each one is for.
Write one plain sentence (at most 160 characters) that says what this repo is and what it is for. Name the key technologies.
No marketing words, no emoji, no leading "This repo". If the README says the repo is archived, start with "Archived:".
Pick the single best category.

Repo: {name}
Primary language: {lang}
Top-level files: {files}

README (may be truncated):
{readme}"""


def summarize(client, repo: dict, text: str, files: list[str]) -> dict | None:
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{
            "role": "user",
            "content": PROMPT.format(
                name=repo["name"],
                lang=repo.get("language") or "unknown",
                files=", ".join(files) or "none",
                readme=text[:20000] or "(no README)",
            ),
        }],
    )
    if response.stop_reason == "refusal":
        print(f"  refused: {repo['name']}", file=sys.stderr)
        return None
    out = json.loads(next(b.text for b in response.content if b.type == "text"))
    out["summary"] = out["summary"].strip()[:DESC_MAX]
    return out


def status(repo: dict, summary: str, text: str, now: datetime) -> str:
    if repo["archived"] or summary.lower().startswith("archived") or "**Archived" in text[:600]:
        return "archived"
    days = (now - datetime.fromisoformat(repo["pushed_at"].replace("Z", "+00:00"))).days
    if days <= 30:
        return "active"
    if days <= 90:
        return "cooling"
    return "dormant"


def main() -> None:
    cache: dict = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    client = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        client = anthropic.Anthropic()

    now = datetime.now(timezone.utc)
    rows, wrote = [], []
    repos = list_repos()
    for repo in repos:
        name, desc = repo["name"], (repo["description"] or "").strip()
        entry = cache.setdefault(name, {})
        sha, text = readme(name)
        hand_written = bool(desc) and desc != entry.get("written_description")

        first_sight = "readme_sha" not in entry  # seeded entries just record the sha
        changed = not first_sight and entry.get("readme_sha") != sha
        needs = (not entry.get("category")) or changed or (not hand_written and not entry.get("summary"))
        if needs and client:
            print(f"summarizing {name}", file=sys.stderr)
            got = summarize(client, repo, text, [] if sha else root_files(name))
            if got:
                entry["category"] = got["category"]
                if not hand_written:
                    entry["summary"] = got["summary"]
        entry["readme_sha"] = sha

        summary = desc if hand_written else (entry.get("summary") or desc)
        if not hand_written and entry.get("summary") and desc != entry["summary"]:
            wrote.append((name, desc, entry["summary"]))
            if WRITE:
                gh(f"/repos/{OWNER}/{name}", "PATCH", {"description": entry["summary"]})
                entry["written_description"] = entry["summary"]

        rows.append({
            "name": name,
            "url": repo["html_url"],
            "private": repo["private"],
            "fork": repo["fork"],
            "language": repo.get("language"),
            "topics": repo.get("topics", []),
            "homepage": repo.get("homepage") or None,
            "summary": summary,
            "category": entry.get("category", "Other"),
            "status": status(repo, summary, text, now),
            "created_at": repo["created_at"],
            "pushed_at": repo["pushed_at"],
            # Private repos show only when they last moved, never what the commit said.
            "last_commit": (lc := last_commit(name)) and ({"date": lc["date"]} if repo["private"] else lc),
        })

    # Forget repos that were deleted or renamed.
    live = {r["name"] for r in repos}
    for gone in set(cache) - live:
        del cache[gone]

    CACHE.write_text(json.dumps(dict(sorted(cache.items())), indent=2, ensure_ascii=False) + "\n")
    rows.sort(key=lambda r: r["pushed_at"], reverse=True)
    OUT.write_text(json.dumps({"owner": OWNER, "generated_at": now.isoformat(timespec="seconds"), "repos": rows}, indent=2, ensure_ascii=False) + "\n")

    verb = "updated" if WRITE else "would update"
    for name, old, new in wrote:
        print(f"{verb} description of {name}: {old!r} -> {new!r}")
    print(f"{len(rows)} repos written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
