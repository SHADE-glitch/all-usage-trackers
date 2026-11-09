# FAMILY_CONTRACT.md — the four usage trackers

> **Canonical.** This is the single source of truth for what the tracker family
> shares and what it is allowed to differ on. The machine-readable summary is
> `scripts/tests/fixtures/family_contract.json`; four byte-identical copies of
> that file, one per repo, are what CI actually checks.
>
> Contract version: **1**.
>
> The four repositories are independent and self-contained. **No runtime shared
> library, no monorepo.** See "Why no shared library" below.

## 0. Members

| key | Repo | Role | What it records | Own sync |
|---|---|---|---|---|
| `cbut` | codebuddy-usage-tracker | tracker | CodeBuddy CLI transcripts | systemd, every 15 min |
| `ocut` | opencode-usage-tracker | tracker | OpenCode CLI host DB + hook sidecar | systemd, every 15 min |
| `qcut` | qoder-cn-usage-tracker | tracker | Qoder CN app + CLI transcripts | systemd, daily |
| `aut` | all-usage-trackers | board (passive consumer) | reads the three indexes; writes no DB | none |

`aut` has no `systemd/` and no `sync` of its own: `aut_sources.py` keeps one
adapter per tracker (`SOURCES`, `Snapshot`, one normalising SQL expression per
source). Adding a tracker means adding one `SOURCES` entry, not changing the TUI.
`aut` is the **verifier** of this contract (`test_family_contract.py`), not a
fourth implementation.

## 1. Common section — must match across the four repos

### 1.1 Tab strip

The three **trackers** expose the same eight tabs, in this order:
`dashboard`, `tools`, `skills`, `agents`, `plugins`, `mcp`, `tokens`, `usage`.
Only the data behind each slot is repo-specific. cbut/ocut declare this as
`ENTITY_TABS`; qcut as `TABS` with `SUMMARY_TABS` / `TABLE_TABS`.

### 1.2 Window presets

`USAGE_RANGES` is copied verbatim in all four repos:
`1d=1, 2d=2, 3d=3, 7d=7, 14d=14, 30d=30, all=None`.
A preset added on one side makes "7d" mean two different things;
`test_cross_repo_golden.py` and `test_family_contract.py` pin this table.

### 1.3 Headless core

Common subcommands: `sync [--full] [--quiet]`, `stats`, `health`, `show`,
`recent`, `inventory`, `export`, `backup`, `restore`, `vacuum`, `format`.
Repo-specific extras are allowed (see the deviations table below).

### 1.4 Sync

Incremental by per-file byte offset, idempotent on call id; `--full` rebuilds
and takes a backup first; `--quiet` suppresses the report only. Each tracker
owns its own source format.

### 1.5 Installer

`install.sh` accepts `--force` and `--no-timer`; is idempotent; refuses to
replace a non-symlink target without `--force`; installs and enables the
systemd timer by default, and skips gracefully when a user-level systemd
instance is unavailable (macOS, WSL, containers, CI).

### 1.6 systemd units

`<key>-sync.service` plus `<key>-sync.timer`, `Type=oneshot`,
`ExecStart=%h/.local/bin/<key> sync --quiet`, `Nice=10`, `Persistent=true`.

### 1.7 Index contract for the board

`aut` reads each tracker's SQLite index read-only. Each adapter needs a
normalised snapshot: sessions, calls, tokens (Usage Total), model rollup and
window buckets. Concrete table and column names differ and are normalised in
`aut_sources.py`.

### 1.8 Contract fixtures

`cross_repo_golden.json` (four byte-identical copies, sha256-pinned) and
`family_contract.json` (four byte-identical copies, version- and sha256-pinned).
CI checks out one repo at a time, so a test must never read a sibling repo's
file: each copy is verified against a digest constant in that same repo.

## 2. Allowed deviations — do not smooth these over

| # | Deviation | Detail |
|---|---|---|
| 2.1 | Board tabs | `aut` has six tabs: `dashboard, tools, skills, tokens, usage, sources`. It is a combined board, not a tracker; `sources` replaces the per-agent / plugin / MCP detail views. |
| 2.2 | No credits column in ocut | OpenCode reports no credit value. `cbut` stores `model_responses.credit`, `qcut` stores `model_calls.credits`; `ocut` has neither. A legitimate absence, not a missing feature. |
| 2.3 | Qoder CN app vs CLI | Qoder's own routes write `credits` and zero for every token field unless the CLI process sets `QODERCN_EXPOSE_TOKEN_USAGE=1`; with it they write real tokens and may still carry credits. BYOK routes report tokens and no credits at all. `row_reports_tokens` renders a route-level zero as `—`; no coverage percentage is stored or shown. |
| 2.4 | Usage Total formulas differ | `cbut` = `prompt + completion + COALESCE(cache_hit, 0)`, NULL if either token part is missing. `ocut` = `prompt + completion + 2*cache_read + cache_write`, NULL only when completion is NULL. `qcut` = `input + output + COALESCE(cache_read, 0)`, NULL if either part is missing. The golden fixture records each repo's own answer rather than one shared number. |
| 2.5 | NULL semantics | A field absent from a response is `NULL`, never a fabricated `0`; a reported `0` stays `0`. Rendering is `-` / `—` per repo. |
| 2.6 | Timer frequency | `cbut` / `ocut` use `OnUnitActiveSec=15m`; `qcut` uses `OnCalendar=daily` plus `RandomizedDelaySec=15m` (deliberate: Qoder's log cadence differs, and a measured `qcut sync` is 0.05 s with no new files). `aut` has no timer. Decided 2026-11-09: keep daily. |
| 2.7 | Headless extras | `ocut` adds `modes`; `qcut` adds `commands`, `env`; `cbut` adds `sessions`. `aut` has its own board commands (`cbut|ocut|qcut`, `sync`, `json`, `skills`). |
| 2.8 | Schema names | `cbut` uses `model_responses` with `prompt_tokens` / `completion_tokens` / `prompt_cache_hit_tokens` / `credit` / `usage_available`; `ocut` and `qcut` use `model_calls` with different column names and `usage_available` / `has_usage`. |
| 2.9 | One token total | Only Usage Total exists as an unnamed token total. Do not reintroduce a second total such as API Total. |

## 3. Why no shared library

`test_cross_repo_golden.py` records the earlier decision verbatim: the fix for
drifting copied expressions is "not a rewrite into a shared library — it is a
golden fixture". The Usage Total expression and typed date entry were copied
between the three trackers and maintained separately; NULL semantics drifted
once between the board and its siblings (P1-12 / P2-17). Four independent
public repos, self-contained with `git pull` updating the live install, about
28k lines and four separate CI suites make a runtime dependency a poor trade
for the three small blocks that are actually identical.

This also follows the owner's standing rule: align the **common section**,
leave each repo's own sections free, never overwrite repo-specific content.

## 4. Changing this contract

1. Edit this canonical file and the canonical `family_contract.json` in
   `all-usage-trackers`.
2. Re-copy `family_contract.json` byte-for-byte into the other three repos.
3. In the same change, bump `contract_version`, recompute the sha256 and update
   the digest constant in all four contract tests.
4. Run all four suites. Append-only: do not renumber existing deviation rows.

A version bump with an unchanged digest, or a digest change in only one repo,
fails CI.
