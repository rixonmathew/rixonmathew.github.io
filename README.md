# rixonmathew.github.io

A catalog of every repo under [github.com/rixonmathew](https://github.com/rixonmathew): what each one
is for, how recently it moved, and which ones need a follow-up. Live at
<https://rixonmathew.github.io>.

- `index.html` is a static page that renders `data/repos.json`.
- `scripts/build_catalog.py` rebuilds `data/repos.json` from the GitHub API.
- `.github/workflows/catalog.yml` runs it daily and on demand (**Actions → Rebuild project catalog → Run workflow**).

## How summaries work

`data/catalog.json` caches one entry per repo. When a repo is new, or its README changes, Claude
writes a one-line summary and picks a category. That summary is written back as the repo's GitHub
description, so it only has to be generated once. A description you wrote by hand is never
overwritten. To pin a category, edit the repo's entry in `data/catalog.json`.

Status comes from the last push: **active** ≤30 days, **cooling** 31–90, **dormant** 90+,
**archived** if GitHub or the README says so.

The latest commit message is shown for public repos only; private repos show just the push date.

## Secrets

| Secret | What it needs |
|---|---|
| `CATALOG_TOKEN` | Fine-grained PAT, all repositories: Metadata read, Contents read, Administration read/write (for descriptions) |
| `ANTHROPIC_API_KEY` | Optional. Without it, new repos are listed with their GitHub description and category "Other" |

Run locally: `GH_TOKEN=$(gh auth token --user rixonmathew) WRITE_DESCRIPTIONS=0 python3 scripts/build_catalog.py`
