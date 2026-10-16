#!/usr/bin/env bash
# SovRing-Labs installer: choose repositories, clone them, install their dependencies, run each quick test.
#
#   ./install.sh --list                  every repository: what it needs and its quick test
#   ./install.sh --dry-run [REPO ...]    print the exact commands, run nothing
#   ./install.sh REPO [REPO ...]         clone into $SOVRING_HOME (default ~/sovring), install deps, run the quick test
#   ./install.sh --all                   every repository whose quick test is short (skips the long Rust / model builds)
#   ./install.sh --gui                   after the tests, open the test-suite browser page (sovring-suite.pyz; fetched once from the release)
#
# Reads repos.json beside this script. Needs bash, git and python3. Nothing runs as root; Python deps go into a .venv inside
# each clone (no system or --user installs).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REG="$DIR/repos.json"
HOME_DIR="${SOVRING_HOME:-$HOME/sovring}"
LONG=" omni-render omni-ui omnid "

command -v python3 >/dev/null || { echo "python3 is required (Python 3.10+): https://www.python.org/downloads/" >&2; exit 1; }
command -v git >/dev/null || { echo "git is required: https://git-scm.com/downloads" >&2; exit 1; }
[ -f "$REG" ] || { echo "repos.json not found beside install.sh ($REG)" >&2; exit 1; }

field() {  # field REPO KEY → value ('' if absent)
  python3 -c 'import json,sys
for r in json.load(open(sys.argv[1]))["repos"]:
    if r["repo"]==sys.argv[2]: v=r.get(sys.argv[3]); print(", ".join(v) if isinstance(v,list) else (v or ""))' "$REG" "$1" "$2"
}
all_repos() { python3 -c 'import json,sys;[print(r["repo"]) for r in json.load(open(sys.argv[1]))["repos"]]' "$REG"; }

DRY=0; GUI=0; LIST=0; SEL=()
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --gui) GUI=1 ;;
    --list) LIST=1 ;;
    --all) while read -r r; do case "$LONG" in *" $r "*) ;; *) SEL+=("$r") ;; esac; done < <(all_repos) ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    -*) echo "unknown option $a (try --help)" >&2; exit 2 ;;
    *) [ -n "$(field "$a" repo)" ] || { echo "unknown repository: $a (try --list)" >&2; exit 2; }; SEL+=("$a") ;;
  esac
done

if [ $LIST -eq 1 ] || { [ ${#SEL[@]} -eq 0 ] && [ $DRY -eq 0 ]; }; then
  printf '%-22s %-28s %s\n' REPOSITORY NEEDS "QUICK TEST"
  while read -r r; do printf '%-22s %-28s %s\n' "$r" "$(field "$r" needs | cut -c1-28)" "$(field "$r" quicktest)"; done < <(all_repos)
  echo; echo "Run: ./install.sh <repository> [...]   or   ./install.sh --all   (--dry-run to see the commands first)"
  exit 0
fi
[ ${#SEL[@]} -eq 0 ] && mapfile -t SEL < <(all_repos)

declare -A RESULT
for r in "${SEL[@]}"; do
  url=$(field "$r" url); setup=$(field "$r" setup); run=$(field "$r" run); expect=$(field "$r" expect)
  note=$(field "$r" quicktest_note); d="$HOME_DIR/$r"
  echo "== $r  ($(field "$r" one_line | cut -c1-90))"
  if [ $DRY -eq 1 ]; then
    echo "   git clone --depth 1 $url $d"
    [ -n "$setup" ] && echo "   (cd $d && $setup)"
    echo "   (cd $d && $run)      # expect: $expect"
    [ -n "$note" ] && echo "   note: $note"
    continue
  fi
  mkdir -p "$HOME_DIR"
  if [ -d "$d/.git" ]; then git -C "$d" pull -q --ff-only || true; else git clone -q --depth 1 "$url" "$d"; fi
  if [ -n "$setup" ]; then
    echo "   setup: $setup"
    (cd "$d" && bash -c "$setup") || echo "   setup step failed (Debian/Ubuntu: sudo apt install python3-venv); the quick test will show what is missing"
  fi
  [ -n "$note" ] && echo "   note: $note"
  echo "   running: $run"
  if (cd "$d" && bash -c "$run"); then RESULT[$r]=PASS; else RESULT[$r]="FAIL (exit $?)"; fi
  echo "   $r quick test: ${RESULT[$r]}   (expect: $expect)"
done

if [ $DRY -eq 0 ]; then
  echo; echo "== summary (clones in $HOME_DIR)"
  for r in "${SEL[@]}"; do printf '   %-22s %s\n' "$r" "${RESULT[$r]}"; done
  echo "What each test means: each repository's suite.json and STATUS.md, or the MCP server (.mcp/README.md)."
fi
if [ $GUI -eq 1 ]; then
  PYZ="$DIR/sovring-suite.pyz"
  if [ ! -f "$PYZ" ]; then   # release asset, not committed: fetch it once
    PYZ="${SOVRING_HOME:-$HOME/sovring}/sovring-suite.pyz"; mkdir -p "$(dirname "$PYZ")"
    [ -f "$PYZ" ] || python3 -c "import sys,urllib.request;urllib.request.urlretrieve(sys.argv[1],sys.argv[2])" \
      "https://github.com/SovRing-Labs/SovRing/releases/latest/download/sovring-suite.pyz" "$PYZ" \
      || { echo "could not download sovring-suite.pyz (release asset)"; exit 1; }
  fi
  exec python3 "$PYZ"
fi
