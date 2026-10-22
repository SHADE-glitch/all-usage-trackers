#!/usr/bin/env bash
#
# install.sh — install or re-install the usage overview from this repo.
#
# Idempotent: re-running is safe. It creates repo/.venv with the TUI dependency
# (textual) and symlinks bin/aut into ~/.local/bin, so `git pull` here updates the
# running install. `aut json` and `aut sync` need only python3; only the board
# needs the venv.
#
#   ./install.sh            install (refuses to replace a real file)
#   ./install.sh --force    also replace an existing non-symlink at the target
#
# Environment overrides (mainly for testing a sandboxed install):
#   AUT_BIN_DIR    default: ~/.local/bin
set -euo pipefail

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help)
      echo "usage: ./install.sh [--force]"
      echo "  --force  replace an existing non-symlink at the install location"
      exit 0
      ;;
    *) echo "install.sh: unknown option '$arg' (try --help)" >&2; exit 2 ;;
  esac
done

SELF="$(readlink -f "${BASH_SOURCE[0]}" 2>/dev/null || true)"
REPO_DIR="$(cd "$(dirname "${SELF:-${BASH_SOURCE[0]}}")" && pwd)"
cd "$REPO_DIR"

BIN_DIR="${AUT_BIN_DIR:-$HOME/.local/bin}"
DST="$BIN_DIR/aut"

# Refuse before doing any work: a venv built and then a refused symlink is a
# half-install that looks like a success in the transcript.
if [ -e "$DST" ] && [ ! -L "$DST" ] && [ "$FORCE" -ne 1 ]; then
  echo "install.sh: refusing to replace '$DST' (exists and is not a symlink)" >&2
  echo "  move or delete it first, or re-run with --force" >&2
  exit 1
fi

# --- 1. TUI virtualenv -----------------------------------------------------
VENV="$REPO_DIR/.venv"
if [ -x "$VENV/bin/python" ]; then
  echo "==> venv already present: $VENV"
else
  echo "==> creating venv: $VENV"
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.13 "$VENV" || uv venv "$VENV"
  else
    python3 -m venv "$VENV"
  fi
fi

echo "==> installing TUI dependencies"
if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$VENV/bin/python" -r "$REPO_DIR/requirements.txt"
else
  # A venv uv created earlier has no pip in it; bootstrap it so the fallback is
  # a real path rather than a dead end.
  if ! "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "==> no pip in $VENV; bootstrapping with ensurepip"
    "$VENV/bin/python" -m ensurepip --upgrade
  fi
  "$VENV/bin/python" -m pip install -r "$REPO_DIR/requirements.txt"
fi

# --- 2. symlink the entry point --------------------------------------------
mkdir -p "$BIN_DIR"
rm -f "$DST"
ln -s "$REPO_DIR/bin/aut" "$DST"
echo "  $DST -> $REPO_DIR/bin/aut"

# --- 3. report what it found ------------------------------------------------
echo
echo "==> aut json --days 7"
"$DST" json --days 7 >/dev/null && echo "  ok" || echo "  (a source reported a problem — run aut json to see it)"

cat <<EOF

Installed.

  aut             open the overview board
  aut cbut        jump straight into one tracker
  aut sync        run the three trackers' own sync commands
  aut json        the same numbers, as JSON

The board reads each tracker's database; it does not replace them. Keep using
cbut / ocut / qcut directly whenever you want their full TUI.
EOF
