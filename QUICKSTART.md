# QUICKSTART — 5 minutes

You need: `git` and `python3` (3.10+). Some repositories also need Node, a C compiler or Rust; the installer and the
MCP server tell you which (see `./install.sh --list`). On Debian/Ubuntu also `sudo apt install python3-venv`.

## Route A — let your coding assistant do it

Paste this into Claude Code, Cursor, opencode, Copilot or any assistant that can browse and run commands:

> Read https://github.com/SovRing-Labs/SovRing (start with `llms.txt`, then `QUICKSTART.md`). Clone it, run
> `./install.sh --list`, pick armilla-astrolabe (or the one I name), run `./install.sh <that repository>` and show me the
> result. Then open that repository's `suite.json` and explain in plain words what the tests prove.

Or connect the MCP server so the assistant has tools for it (explain, check readiness, clone, quick test, list tests,
run one test, show evidence):

```bash
git clone --depth 1 https://github.com/SovRing-Labs/SovRing ~/sovring/SovRing
claude mcp add sovring -e SOVRING_HOME=$HOME/sovring -- python3 $HOME/sovring/SovRing/.mcp/server.py
```
Other clients: `.mcp/client.config.example.json`. Details: `.mcp/README.md`.

## Route B — three commands yourself

```bash
git clone --depth 1 https://github.com/SovRing-Labs/SovRing && cd SovRing
./install.sh --dry-run armilla-astrolabe     # shows exactly what it will run
./install.sh armilla-astrolabe               # clone into ~/sovring, Python deps into a .venv there, run the quick test
```
Expected: the line `armilla-astrolabe quick test: PASS` and a summary row `armilla-astrolabe PASS`. `./install.sh --all` does every repository with a short quick test
(it skips the Rust browser and omnid, which need a long build; their `AGENTS.md` has the steps).

Or one repository on its own, without the umbrella (each repository's `AGENTS.md` has its three commands):

```bash
git clone --depth 1 https://github.com/SovRing-Labs/armilla-astrolabe && cd armilla-astrolabe
python3 -m venv .venv && . .venv/bin/activate && python -m pip install -q numpy pytest
PYTHONPATH=engine python3 -m pytest -q engine/tests       # expect: 9 passed
```

## What next

- **What does a test prove?** `suites/<repo>/suite.json` here (later also in each repository): every claim with its verify command, the expected output,
  *what it means*, *how we got it*, *how you can use it in your own work*, and its honest limits.
- **Is it working today?** `STATUS.md` here (one row per repository) and in each repository.
- **Where do the numbers come from?** `DOSSIER.md` (history, metrics, limits) and `TECHNICAL-DISCLOSURE.md` (the method)
  in each repository; the research papers and their harness in `omniring-research`.
- **Cite it:** each repository's `CITATION.cff` (Zenodo DOI).

## If something fails

| You see | Do |
|---|---|
| `error: externally-managed-environment` | you ran pip outside a venv; use the `.venv` line above (the installer does) |
| `No module named venv` / `ensurepip` | Debian/Ubuntu: `sudo apt install python3-venv` |
| `node: bad option: --experimental-strip-types` (cost-savers) | install Node 22.6+ (nodejs.org) |
| a test is marked SKIP for a CPU flag | your CPU lacks that instruction set (e.g. AVX-512); the result file is still in the repository |
| anything else | `./install.sh --dry-run <repo>` shows each command; run them one by one, or ask the MCP server `check_readiness` |

## The complete catalog

`./install.sh --list` and the MCP `explain` tool discover the same 26 repositories: 12 original public repositories and 14 local E exports. The E public URLs await publication. `./install.sh --dry-run REPO` prints setup before running it. Local suite PASS means the stated check passed; EXTERNAL rows and scientific negatives remain limitations. See STATUS.md and each suite.json.
