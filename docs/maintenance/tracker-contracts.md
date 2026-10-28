# The three tracker contracts `aut` reads

`aut` has no database of its own. Every number on the board is read, read-only, out of a SQLite
index that one of the three trackers built:

    ~/.local/share/<db_name>/usage.db

This file is the single place that states what each adapter assumes. `scripts/aut_sources.py` is the
code; if the two disagree, the code is right and this file is a bug. Adding a fourth tracker means
adding a row here and one `Source` entry there — nothing in the TUI learns a column name.

## Where the file is and which table is read

| Tracker | `db_name` | Table | Cost unit | "A real number" flag |
|---|---|---|---|---|
| `cbut` — CodeBuddy | `codebuddy-usage-tracker` | `model_responses` | `cr` (credits) | `usage_available` |
| `ocut` — OpenCode | `opencode-usage-tracker` | `model_calls` | `$` (dollars) | `usage_available` |
| `qcut` — Qoder CN | `qoder-cn-usage-tracker` | `model_calls` | `cr` (credits) | `has_usage` |

Two of the three share a table name and none of the three shares a column set, which is why the
normalisation is one SQL expression per source instead of one Python branch per tracker.

## Token columns

| Tracker | input | output | cache read | cache write |
|---|---|---|---|---|
| `cbut` | `prompt_tokens` | `completion_tokens` | `cache_read_input_tokens` | `cache_creation_input_tokens` |
| `ocut` | `prompt_tokens` | `completion_tokens` | `cache_read` | `cache_write` |
| `qcut` | `input_tokens` | `output_tokens` | `cache_read_tokens` | `cache_creation_tokens` |

## The usage total, per tracker

The board prints **one** token figure and calls it *usage total*. It is not the same expression in
the three sources, because each tracker defines it for its own panels and `aut` re-states that
definition rather than inventing a fourth one:

- `cbut` — `prompt + completion + cache hit`. The cache hit is the display-only re-add the family
  uses; the provider's API total is not surfaced anywhere.
- `ocut` — `prompt + completion + 2 × cache_read + cache_write`. `ocut` reports an **uncached**
  prompt, so the full prompt is `prompt + read + write`, and the read is then re-added once more to
  land on the same shape as `cbut`'s number.
- `qcut` — `input + output + cache_read`.

A change here is the one that can silently make two screens disagree: the KPI strip, the per-day
buckets, the model ranking and the drill-down all read `expr_total`, so they cannot drift from each
other — but they can drift from the tracker they claim to describe.

## Project column

| Tracker | Expression | Why |
|---|---|---|
| `cbut` | `project` | the path is already a directory |
| `ocut` | `NULLIF(directory, '')`, then `project` | `project` holds a hashed id; the directory is the readable one |
| `qcut` | `project` | `cwd` lives on its `sessions` table, not on the call row |

## Direct skill reads (`skill_reads`)

Each tracker also records direct reads of a skill card: one row per `Read`/`read`
tool call whose path ends in `/SKILL.md`. The table is `skill_reads` in all
three indexes, with `call_id`, `skill`, `session_id`, `project`, `ts`, `status`
and `duration_ms`. `skill` is the card's parent directory; the path itself is
not stored.

This is deliberately **not** folded into `skill_usage`: every existing count
over that table answers "how many times was the skill invoked", and a read is a
different mechanism. `aut` merges reads by name beside the calls and shows them
in their own column.

A tracker built before cbut v14 / ocut v4 / qcut v4 has no such table. The read
count is then **unknown** — `—` beside the row and a "direct reads unavailable"
line naming the source — never a zero. The trackers release their sync cursor on
that upgrade, so the next sync re-reads the transcripts and backfills the reads.

## What breaks, and how it looks

| Upstream change | What `aut` shows |
|---|---|
| table or column renamed / dropped | that source's `error` badge — the SQL raises, the exception is caught per source |
| a column only the merges read is dropped (`provider`, `status`, `duration_ms`) | the same badge: `Source` prepares one SELECT naming the merge columns at open, and `aut_model` records a failed merge query per source, so a tab cannot be silently empty beside an `ok` row |
| index file missing or never built | `missing` — **not** a zero |
| no calls in a week | `idle` — deliberately a different word from `broken` |
| column still present but no longer written | a plausible **0** — the quiet case; only an L1 check against a copied index catches it |
| a new token column added upstream | ignored until `expr_total` and the split columns name it |
| `skill_reads` missing (a tracker not yet upgraded) | the reads column shows `—` and the footer says `direct reads unavailable: <key> (no table)` — not a zero |
