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

## Credentials

**GitHub** (repo secret `CATALOG_TOKEN`): a fine-grained PAT with access to all repositories and the
permissions Metadata read, Contents read, Administration read/write (Administration is what allows editing
descriptions). The workflow's built-in `GITHUB_TOKEN` can't see other private repos.

**Claude** uses Workload Identity Federation, so no API key is stored. The job requests a GitHub OIDC
token (`id-token: write`) and the Anthropic SDK exchanges it for a short-lived token. Set these as
repo **variables** (not secrets); the IDs come from the Claude Console's *Connect workload → GitHub Actions* wizard:

| Variable | Value |
|---|---|
| `ANTHROPIC_FEDERATION_RULE_ID` | `fdrl_...` |
| `ANTHROPIC_ORGANIZATION_ID` | your organization UUID |
| `ANTHROPIC_SERVICE_ACCOUNT_ID` | `svac_...` |
| `ANTHROPIC_WORKSPACE_ID` | `wrkspc_...` (needed when the rule covers more than one workspace) |

The federation rule should match only this repo's `main` branch: subject prefix
`repo:rixonmathew/rixonmathew.github.io:ref:refs/heads/main`, audience `https://api.anthropic.com`,
claim `repository_owner: rixonmathew`. Without these variables the catalog still rebuilds; new repos just
get their GitHub description and category "Other".

Run locally: `GH_TOKEN=$(gh auth token --user rixonmathew) WRITE_DESCRIPTIONS=0 python3 scripts/build_catalog.py`
