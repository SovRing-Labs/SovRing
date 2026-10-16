# sovring MCP server

A small MCP server that lets your coding assistant explain the SovRing-Labs repositories, check your machine, clone a
repository, run its quick test and show what each test proves. One Python file, standard library only (Python 3.8+), no
`pip install`. It speaks MCP over stdio (newline-delimited JSON-RPC 2.0).

## Connect it (1 minute)

```bash
git clone --depth 1 https://github.com/SovRing-Labs/SovRing ~/sovring/SovRing
python3 ~/sovring/SovRing/.mcp/server.py --selftest          # prints: sovring-mcp selftest OK: 8 tools, 12 repos
claude mcp add sovring -e SOVRING_HOME=$HOME/sovring -- python3 $HOME/sovring/SovRing/.mcp/server.py
```
Cursor, opencode and Claude Desktop: copy your client's block from `client.config.example.json` (use absolute paths).
Then ask your assistant: *"Use the sovring tools: explain SovRing, check my readiness, then set up and quick-test
armilla-astrolabe and tell me what the test proves."*

**No install at all:** `https://gitmcp.io/SovRing-Labs/SovRing` (or `https://gitmcp.io/SovRing-Labs/<repo>`) is a free,
read-only docs endpoint built from the public repository by GitMCP. It can read the docs; it cannot run tests.

## Tools

| Tool | Tier | What it does |
|---|---|---|
| `explain(repo?, level?)` | discovery | what SovRing-Labs is, or what one repository does; `beginner` / `intermediate` / `advanced` |
| `check_readiness(repo?)` | setup | Python, git, venv support, Node, Rust, compilers, CPU flags (AVX2 …) per repository, with the fix for each gap |
| `setup_steps(repo)` | setup | the exact commands: clone, install, quick test |
| `fetch_repo(repo)` | setup | clone (or update) the repository into `$SOVRING_HOME` (default `~/sovring`) |
| `quick_test(repo)` | setup | first time: create `.venv` in the clone and install its Python deps; then run the quick test → PASS/FAIL + last lines |
| `list_tests(repo)` | verification | every claim in the repository's `suite.json`: what it means, how to use it |
| `run_test(repo, test_id)` | verification | run one claim's verify command (or `quicktest`) and compare with the expected output |
| `get_evidence(repo, test_id)` | verification | how the number was obtained, honest limits, corrections, and the start of the committed evidence file |

## What it runs, and where

Only the commands written in `repos.json` (setup, quick test) and in each repository's `suite.json` (verify), only inside
the clone under `$SOVRING_HOME`, and only when you (or your assistant) call `fetch_repo`, `quick_test` or `run_test`. Python
dependencies go into a `.venv` inside the clone — never into your system Python. Nothing needs root. Network: `git clone`
and `pip install` only.

## Data it reads

`repos.json` in the umbrella root (generated from the public repositories by `tools/gen-agents-md.py`), then each clone's
`suite.json`, else the umbrella's `suites/<repo>/suite.json`.
