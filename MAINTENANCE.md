# MAINTENANCE.md — all-usage-trackers

Procedure file. This is a **router**: the long-form maintenance asset lives under
[`docs/maintenance/`](docs/maintenance/tracker-contracts.md) (committed), and the rules for working
in this repository live in [`AGENTS.md`](AGENTS.md). Do not duplicate their tables here — a
duplicated fact is the thing that drifts.

The one maintenance risk that matters: **one of the three trackers changing its index**. `aut` owns
no schema of its own — it reads each tracker's `usage.db` through the six SQL expressions in
`scripts/aut_sources.py`. A renamed table or column raises and surfaces as that source's
`error` badge, which is loud. The quiet case is a column that still exists and stops being
populated: the expression keeps working, the number becomes 0, and the board looks healthy. The
contract each adapter assumes — table, columns, total definition, cost unit, project column — is in
[`docs/maintenance/tracker-contracts.md`](docs/maintenance/tracker-contracts.md).

## Verification tiers

- **L0** — `python3 -m unittest discover -s scripts/tests` (fixture databases in a temp `HOME`, no
  host state).
- **L1** — a throwaway `HOME` holding copies of the three indexes, so the real aggregation runs
  without touching the live databases.
- **L2** — the real `~/.local/share/*/usage.db` files; needs the owner's go-ahead.

## CI

`.github/workflows/ci.yml` runs the L0 layer on a Python 3.11 / 3.14 matrix.

## The four questions a change here must answer

1. **Which tracker contract does this touch?** If none, the change belongs in `aut_model.py` or the
   app, not in an adapter.
2. **Is the usage total still the tracker's own?** The three totals are re-stated per source
   (see the contracts file); a figure that quietly switches to the provider's API total is the
   failure the 0.5.0 release note records.
3. **Does a missing index still read as missing, not as zero?** `—` and `0` are different answers.
4. **Did the footer change?** A key that is drawn must act, and a key that acts must be drawn;
   `check_action` is the single place that decides both.

## After a change

- Add a `D-###` entry to [`CHANGELOG.md`](CHANGELOG.md) when the change is not a plain `feat`.
- Re-run L0. A green L0 with no fixture for the thing you changed proves nothing.
