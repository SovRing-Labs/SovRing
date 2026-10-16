#!/usr/bin/env python3
"""sovring-mcp — stdio MCP server that walks a person (or their coding assistant) through the SovRing-Labs repos.

Python 3.8+ standard library only. Newline-delimited JSON-RPC 2.0 over stdin/stdout (MCP stdio transport).
Tiers follow the SovRing design: discovery (explain) → setup (check_readiness, setup_steps, fetch_repo, quick_test)
→ verification (list_tests, run_test, get_evidence).

Data it reads, in order:
  repos.json                    the umbrella registry (beside this file's parent: <umbrella>/repos.json)
  <home>/<repo>/suite.json      the repo's own test suite, once cloned (REPO-ACCESS B1 schema)
  <umbrella>/suites/<repo>/suite.json   the umbrella's copy, for repos whose suite is not yet in the repo
Clones go to $SOVRING_HOME (default ~/sovring). Commands run only inside those clones, only the commands written in
repos.json / suite.json, and only when a tool named run_test / quick_test / fetch_repo is called.

Usage: python3 server.py            (stdio, for an MCP client)
       python3 server.py --selftest (offline checks of the tool layer, exit 0 = OK)
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UMBRELLA = os.environ.get("SOVRING_UMBRELLA") or os.path.dirname(HERE)
HOME = os.path.expanduser(os.environ.get("SOVRING_HOME", "~/sovring"))
PROTOCOL = "2025-06-18"
VERSION = "0.1.0"


def registry():
    for p in (os.path.join(UMBRELLA, "repos.json"), os.path.join(HERE, "repos.json")):
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    raise RuntimeError("repos.json not found beside the server (looked in %s)" % UMBRELLA)


def repo_entry(name):
    reg = registry()
    for r in reg["repos"]:
        if r["repo"] == name:
            return reg, r
    raise ValueError("unknown repo %r; known: %s" % (name, ", ".join(r["repo"] for r in reg["repos"])))


def clone_dir(name):
    return os.path.join(HOME, name)


def suite(name):
    for p in (os.path.join(clone_dir(name), "suite.json"), os.path.join(UMBRELLA, "suites", name, "suite.json")):
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f), p
    return None, None


def sh(cmd, cwd, timeout):
    try:
        r = subprocess.run(["bash", "-c", cmd], cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"")
        out = out.decode(errors="replace") if isinstance(out, bytes) else out
        return 124, out + "\n[timed out after %ss]" % timeout


def tail(text, n=25):
    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------- readiness probes
def _version(cmd, rx=r"(\d+)\.(\d+)"):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        m = re.search(rx, out.stdout + out.stderr)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    except Exception:
        return (0, 0)


def _pymod(mod):
    return subprocess.run([sys.executable, "-c", "import " + mod], capture_output=True).returncode == 0


def _cpu_flags():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("flags"):
                    return set(line.split(":", 1)[1].split())
    except OSError:
        pass
    return set()


FIX = {
    "python3": "install Python 3.10+ from python.org or your package manager",
    "git": "install git (apt install git / brew install git / git-scm.com)",
    "gcc": "install a C compiler (apt install build-essential / xcode-select --install)",
    "g++": "install a C++ compiler (apt install build-essential)",
    "make": "install make (apt install make)",
    "node": "install Node.js (nodejs.org; cost-savers needs 22.6+)",
    "cargo": "install Rust (https://rustup.rs: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh)",
}


def need_ok(need, flags):
    """One requirement string from repos.json → (ok, detail, fix)."""
    m = re.match(r"^(python3|node)>=(\d+)(?:\.(\d+))?$", need)
    if m:
        tool, want = m.group(1), (int(m.group(2)), int(m.group(3) or 0))
        have = (sys.version_info[0], sys.version_info[1]) if tool == "python3" else _version(["node", "--version"])
        if have is None:
            return False, "%s not found" % tool, FIX[tool]
        return have >= want, "%s %d.%d (need %d.%d)" % (tool, have[0], have[1], want[0], want[1]), FIX[tool]
    if need.startswith("cpu:"):
        flag = need[4:]
        if platform.machine() not in ("x86_64", "AMD64"):
            return False, "%s needs an x86-64 CPU (this is %s)" % (flag, platform.machine()), "use an x86-64 machine"
        return flag in flags, "cpu flag %s %s" % (flag, "present" if flag in flags else "missing"), "a CPU with %s" % flag
    if need in ("numpy", "pytest", "pyte"):  # installed by the repo's setup step into <clone>/.venv
        ok = _pymod("venv") and _pymod("ensurepip")
        return ok, "python module %s (setup installs it into .venv; venv support %s)" % (
            need, "present" if ok else "missing"), "Debian/Ubuntu: sudo apt install python3-venv"
    if need in FIX:
        ok = shutil.which(need) is not None
        return ok, "%s %s" % (need, "found" if ok else "not found"), FIX[need]
    return None, need + " (check by hand)", "see the repo README"


# ---------------------------------------------------------------- tools
def t_explain(repo=None, level="beginner"):
    reg = registry()
    if not repo:
        out = [reg["about"][level if level in reg["about"] else "beginner"], "", "Repositories:"]
        for r in reg["repos"]:
            out.append("- %s (%s): %s" % (r["repo"], r["group"], r["one_line"]))
        out += ["", "Next: call check_readiness, then setup_steps(repo) for the one that interests you. "
                    "Every claim has a test: list_tests(repo)."]
        return "\n".join(out)
    _, r = repo_entry(repo)
    out = ["%s — %s" % (r["repo"], r["one_line"]), "Licence: %s" % r["licence"],
           "Source: %s" % r["url"] + ("  ·  DOI %s" % r["doi"] if r.get("doi") else "")]
    if level in ("intermediate", "advanced") and r.get("summary"):
        out += ["", r["summary"]]
    if level == "advanced":
        out += ["", "Read next (raw, assistant-friendly):"] + ["- " + u for u in r.get("read_next", [])]
        if r.get("limits"):
            out += ["", "Honest limits (DOSSIER): " + r["limits"]]
    out += ["", "Quick test: %s  (expect: %s; measured %ss on a 2019 laptop)" %
            (r["quicktest"], r["expect"], r.get("quicktest_s", "?"))]
    if r.get("quicktest_note"):
        out.append("Note: " + r["quicktest_note"])
    return "\n".join(out)


def t_check_readiness(repo=None):
    reg = registry()
    flags = _cpu_flags()
    base = ["python3>=3.10", "git"]
    targets = [repo_entry(repo)[1]] if repo else reg["repos"]
    lines = ["Machine: %s %s, Python %s" % (platform.system(), platform.machine(), platform.python_version())]
    for need in base:
        ok, det, fix = need_ok(need, flags)
        lines.append("%s %s%s" % ("OK  " if ok else "MISS", det, "" if ok else "  → " + fix))
    for r in targets:
        miss = []
        for need in r["needs"]:
            ok, det, fix = need_ok(need, flags)
            if ok is False:
                miss.append("%s → %s" % (det, fix))
            elif ok is None:
                miss.append("CHECK " + det)
        state = "READY" if not miss else ("CHECK" if all(m.startswith("CHECK") for m in miss) else "NOT READY")
        lines.append("%-22s %s%s" % (r["repo"], state, "" if not miss else ": " + "; ".join(miss)))
    return "\n".join(lines)


def t_setup_steps(repo):
    reg, r = repo_entry(repo)
    d = clone_dir(repo)
    steps = ["# %s — setup (copy and run each line, or call fetch_repo then quick_test)" % repo,
             "git clone --depth 1 %s %s" % (r["url"], d), "cd %s" % d]
    if r.get("setup"):
        steps.append(r["setup"])
    steps.append(r["quicktest"] + "   # expect: " + r["expect"])
    if r.get("gui"):
        steps.append(r["gui"])
    if r.get("quicktest_note"):
        steps.append("# note: " + r["quicktest_note"])
    if r.get("full_test"):
        steps.append("# full suite: " + r["full_test"])
    steps.append("# what each test means: list_tests(%r)  ·  honest status: %s/blob/main/STATUS.md" % (repo, r["url"]))
    return "\n".join(steps)


def t_fetch_repo(repo):
    _, r = repo_entry(repo)
    d = clone_dir(repo)
    if os.path.isdir(os.path.join(d, ".git")):
        ec, out = sh("git pull --ff-only -q", d, 120)
        return "already cloned at %s (git pull exit %d)" % (d, ec)
    os.makedirs(HOME, exist_ok=True)
    ec, out = sh("git clone -q --depth 1 %s %s" % (r["url"], d), HOME, 600)
    return ("cloned %s → %s" % (r["url"], d)) if ec == 0 else ("clone FAILED (exit %d)\n%s" % (ec, tail(out)))


def _need_clone(repo):
    d = clone_dir(repo)
    if not os.path.isdir(d):
        raise ValueError("%s is not cloned yet; call fetch_repo(%r) first (it clones into %s)" % (repo, repo, d))
    return d


def t_quick_test(repo, timeout_s=900):
    _, r = repo_entry(repo)
    d = _need_clone(repo)
    pre = ""
    if r.get("setup") and not os.path.exists(os.path.join(d, ".sovring-setup-ok")):
        ec, out = sh(r["setup"], d, 900)
        if ec != 0:
            return ("%s setup FAILED (exit %d): %s\n%s\nDebian/Ubuntu without venv support: sudo apt install python3-venv"
                    % (repo, ec, r["setup"], tail(out)))
        open(os.path.join(d, ".sovring-setup-ok"), "w").close()
        pre = "setup done: %s\n" % r["setup"]
    ec, out = sh(r["run"], d, int(timeout_s))
    return "%s%s quick test: %s (exit %d)\ncommand: %s\nexpect: %s\n--- last lines ---\n%s" % (
        pre, repo, "PASS" if ec == 0 else "FAIL", ec, r["run"], r["expect"], tail(out))


def t_list_tests(repo):
    _, r = repo_entry(repo)
    s, path = suite(repo)
    if not s:
        return ("%s has no suite.json yet; its quick test is: %s (expect %s). "
                "Call quick_test(%r) after fetch_repo." % (repo, r["quicktest"], r["expect"], repo))
    out = ["%s — %d tests (from %s)" % (repo, len(s["tests"]), path)]
    for t in s["tests"]:
        out.append("\n[%s] %s  (kind %s, ~%ss)\n  claim: %s\n  what it means: %s\n  use it: %s" % (
            t["id"], t["title"], t["kind"], t.get("runtime_s", "?"), t["claim"], t["what_it_means"],
            t["use_in_your_work"]))
    return "\n".join(out)


def _test(repo, test_id):
    s, path = suite(repo)
    if not s:
        raise ValueError("%s has no suite.json yet; use quick_test(%r)" % (repo, repo))
    for t in s["tests"]:
        if t["id"].lower() == str(test_id).lower():
            return t
    raise ValueError("no test %r in %s; ids: %s" % (test_id, repo, ", ".join(t["id"] for t in s["tests"])))


def _cpu_skip(t):
    missing = [f for f in t.get("cpu_flags", []) if f not in _cpu_flags()]
    return ("SKIP: this CPU lacks %s" % ", ".join(missing)) if missing else None


def t_run_test(repo, test_id):
    if str(test_id).lower() == "quicktest":
        return t_quick_test(repo)
    t = _test(repo, test_id)
    if t["kind"] == "external":
        return "[%s] not runnable here (kind external): %s\nevidence: %s" % (t["id"], t["claim"], ", ".join(t["evidence"]))
    skip = _cpu_skip(t)
    if skip:
        return "[%s] %s" % (t["id"], skip)
    d = _need_clone(repo)
    venv = ". .venv/bin/activate && " if os.path.exists(os.path.join(d, ".venv", "bin", "activate")) else ""
    ec, out = sh(venv + t["verify"], d, max(60, int(t.get("runtime_s", 60)) * 10))
    return "[%s] %s (exit %d)\nclaim: %s\nexpect: %s\n--- last lines ---\n%s" % (
        t["id"], "PASS" if ec == 0 else "FAIL", ec, t["claim"], t["expect"], tail(out, 15))


def t_get_evidence(repo, test_id):
    t = _test(repo, test_id)
    _, r = repo_entry(repo)
    out = ["[%s] %s" % (t["id"], t["title"]), "claim: " + t["claim"], "how we got it: " + t["how_we_got_it"]]
    if t.get("honest_limits"):
        out.append("honest limits: " + t["honest_limits"])
    if t.get("corrections"):
        out.append("corrections that touch it: " + ", ".join(t["corrections"]))
    d = clone_dir(repo)
    for ev in t["evidence"]:
        p = os.path.join(d, ev)
        if os.path.isfile(p):
            with open(p, errors="replace") as f:
                body = f.read(1500)
            out.append("--- %s (first 1500 bytes) ---\n%s" % (ev, body))
        else:
            out.append("evidence: %s/blob/main/%s" % (r["url"], ev))
    return "\n".join(out)


REPO = {"type": "string", "description": "repository name, e.g. armilla-astrolabe (explain() with no repo lists them)"}
TOOLS = [
    ("explain", t_explain, "Start here. What SovRing-Labs is, or what one repo does, at a chosen depth.",
     {"repo": REPO, "level": {"type": "string", "enum": ["beginner", "intermediate", "advanced"]}}, []),
    ("check_readiness", t_check_readiness, "Check this machine for what each repo needs (Python, numpy, Node, Rust, "
     "CPU flags) and say how to fix what is missing.", {"repo": REPO}, []),
    ("setup_steps", t_setup_steps, "The exact commands to clone, install and quick-test one repo.", {"repo": REPO}, ["repo"]),
    ("fetch_repo", t_fetch_repo, "Clone (or update) one repo into $SOVRING_HOME (default ~/sovring).", {"repo": REPO}, ["repo"]),
    ("quick_test", t_quick_test, "Run the repo's quick test in its clone and report PASS/FAIL with the last output lines.",
     {"repo": REPO, "timeout_s": {"type": "integer"}}, ["repo"]),
    ("list_tests", t_list_tests, "List the repo's verifiable claims: each test's claim, what it means and how to use it.",
     {"repo": REPO}, ["repo"]),
    ("run_test", t_run_test, "Run one test from the repo's suite.json (or id 'quicktest') and compare with the expected result.",
     {"repo": REPO, "test_id": {"type": "string"}}, ["repo", "test_id"]),
    ("get_evidence", t_get_evidence, "Show how a result was obtained and the start of its committed evidence file.",
     {"repo": REPO, "test_id": {"type": "string"}}, ["repo", "test_id"]),
]


def tool_list():
    return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": req}}
            for n, _, d, p, req in TOOLS]


def call(name, args):
    for n, fn, *_ in TOOLS:
        if n == name:
            try:
                return {"content": [{"type": "text", "text": fn(**(args or {}))}], "isError": False}
            except Exception as e:  # tool errors go back to the assistant as text, the server keeps running
                return {"content": [{"type": "text", "text": "error: %s" % e}], "isError": True}
    raise KeyError(name)


def handle(msg):
    mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
    if mid is None:  # notification (notifications/initialized, cancelled …): no reply
        return None
    try:
        if method == "initialize":
            res = {"protocolVersion": params.get("protocolVersion", PROTOCOL), "capabilities": {"tools": {}},
                   "serverInfo": {"name": "sovring", "version": VERSION},
                   "instructions": "Call explain first, then check_readiness, setup_steps(repo), fetch_repo(repo), "
                                   "quick_test(repo). list_tests / run_test / get_evidence show each claim and its proof."}
        elif method == "ping":
            res = {}
        elif method == "tools/list":
            res = {"tools": tool_list()}
        elif method == "tools/call":
            try:
                res = call(params.get("name"), params.get("arguments"))
            except KeyError:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool %r" % params.get("name")}}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "method not found: %s" % method}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


def serve():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


def selftest():
    reg = registry()
    assert reg["repos"], "registry empty"
    names = [t["name"] for t in tool_list()]
    assert len(names) == len(set(names)) == 8, names
    r = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL}})
    assert r["result"]["serverInfo"]["name"] == "sovring"
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert "armilla-astrolabe" in call("explain", {})["content"][0]["text"]
    assert call("explain", {"repo": "nope"})["isError"]
    assert "git clone" in call("setup_steps", {"repo": reg["repos"][0]["repo"]})["content"][0]["text"]
    assert "Machine:" in call("check_readiness", {})["content"][0]["text"]
    assert handle({"jsonrpc": "2.0", "id": 2, "method": "bogus"})["error"]["code"] == -32601
    print("sovring-mcp selftest OK: %d tools, %d repos" % (len(names), len(reg["repos"])))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        serve()
