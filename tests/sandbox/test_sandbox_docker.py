#!/usr/bin/env python3
"""
test_sandbox_docker.py — Docker isolation test suite for the MRPL Python sandbox.

Covers all tests specified in Phase 2 requirements.

Run from the project root:
    python3 test_sandbox_docker.py

The Docker daemon must be running and the mrpl-sandbox image must be built:
    docker build -t mrpl-sandbox:latest sandbox/
"""

import sys
import os
import subprocess
import time

# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sandbox.executor import run_sandboxed, _docker_available, _image_exists, SANDBOX_IMAGE

# ─── ANSI helpers ─────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

_passed = 0
_failed = 0
_warned = 0

def header(n: int, desc: str):
    print(f"\n{BOLD}{CYAN}{'━'*64}{RESET}")
    print(f"{BOLD}  TEST {n:>2}: {desc}{RESET}")
    print(f"{BOLD}{CYAN}{'━'*64}{RESET}")

def check(label: str, condition: bool, detail: str = "", warn_only: bool = False):
    global _passed, _failed, _warned
    if condition:
        print(f"  {GREEN}✅ PASS{RESET}  {label}")
        _passed += 1
    elif warn_only:
        print(f"  {YELLOW}⚠️  WARN{RESET}  {label}")
        _warned += 1
        if detail:
            print(f"         {DIM}{detail}{RESET}")
    else:
        print(f"  {RED}❌ FAIL{RESET}  {label}")
        _failed += 1
        if detail:
            print(f"         {DIM}{detail}{RESET}")

def show(result: str, max_lines: int = 15):
    lines = result.splitlines()
    for line in lines[:max_lines]:
        print(f"  {DIM}│{RESET} {line}")
    if len(lines) > max_lines:
        print(f"  {DIM}│ ... ({len(lines) - max_lines} more lines){RESET}")
    print()

# ─── Pre-flight checks ────────────────────────────────────────────────────────
print(f"\n{BOLD}{'═'*64}{RESET}")
print(f"{BOLD}  MRPL AI Workbench — Docker Sandbox Test Suite{RESET}")
print(f"{BOLD}{'═'*64}{RESET}")

if not _docker_available():
    print(f"\n{RED}{BOLD}ABORT: Docker is not available. Start Docker Desktop and retry.{RESET}\n")
    sys.exit(1)

if not _image_exists():
    print(f"\n{YELLOW}Sandbox image '{SANDBOX_IMAGE}' not found. Building...{RESET}")
    from sandbox.executor import build_sandbox_image
    ok, msg = build_sandbox_image()
    if not ok:
        print(f"{RED}ABORT: Could not build image: {msg}{RESET}\n")
        sys.exit(1)
    print(f"{GREEN}Image built.{RESET}\n")
else:
    print(f"\n{GREEN}✅ Docker available. Image '{SANDBOX_IMAGE}' found.{RESET}\n")

# ─── Test 1: Basic computation ─────────────────────────────────────────────────
header(1, "Basic computation: print(2 + 2)")
result = run_sandboxed("print(2 + 2)")
show(result)
check("Exit code 0",        "Exit code: 0" in result)
check("STDOUT contains '4'", "4" in result.split("STDOUT:")[-1].split("STDERR:")[0])
check("STDERR is empty",    "(empty)" in result.split("STDERR:")[-1])

# ─── Test 2: Math stdlib import ───────────────────────────────────────────────
header(2, "Math stdlib: import math; print(math.sqrt(144))")
result = run_sandboxed("import math\nprint(math.sqrt(144))")
show(result)
check("Exit code 0",            "Exit code: 0" in result)
check("STDOUT contains '12.0'", "12.0" in result)

# ─── Test 3: Python exception ─────────────────────────────────────────────────
header(3, "Python exception: raise ValueError('test error')")
result = run_sandboxed("raise ValueError('test error')")
show(result)
check("Exit code 1",               "Exit code: 1" in result)
check("STDERR has 'ValueError'",   "ValueError" in result)
check("STDERR has 'test error'",   "test error" in result)
check("STDOUT is empty",           "(empty)" in result.split("STDOUT:")[-1].split("STDERR:")[0])

# ─── Test 4: Infinite loop → timeout ──────────────────────────────────────────
header(4, "Timeout: while True: pass  (waits 10 s)")
print(f"  {DIM}(This test intentionally takes ~10 seconds...){RESET}")
t0 = time.time()
result = run_sandboxed("while True:\n    pass")
elapsed = time.time() - t0
show(result)
check("Returns timeout message",    "timed out" in result.lower(), result)
check("Container was stopped",      "stopped" in result.lower() or "timed out" in result.lower())
check("Elapsed ≥ 10s",             elapsed >= 9.5, f"elapsed={elapsed:.1f}s")
check("Elapsed ≤ 15s (no hang)",   elapsed <= 15, f"elapsed={elapsed:.1f}s")

# ─── Test 5: Large output → truncation ────────────────────────────────────────
header(5, "Output bomb: print('A' * 2_000_000)")
result = run_sandboxed("print('A' * 2_000_000)")
result_size = len(result.encode("utf-8"))
show(result, max_lines=5)
print(f"  {DIM}Result size: {result_size:,} bytes{RESET}\n")
check("Output marked 'truncated'",    "truncated" in result.lower())
check("Result ≤ ~1.1 MB",            result_size <= 1_100_000, f"got {result_size:,} bytes")

# ─── Test 6: Network isolation — external host ─────────────────────────────────
header(6, "Network isolation: connect to example.com:80")
result = run_sandboxed("""\
import socket
try:
    s = socket.create_connection(("example.com", 80), timeout=3)
    s.close()
    print("NETWORK_OPEN")
except Exception as e:
    print("NETWORK_BLOCKED:", e)
""")
show(result)
check("'example.com' connection blocked", "NETWORK_OPEN" not in result, result)
check("Error message present",           "NETWORK_BLOCKED" in result or "NETWORK_OPEN" not in result)

# ─── Test 7: Localhost isolation ─────────────────────────────────────────────
header(7, "Localhost isolation: connect to 127.0.0.1:11434 (Ollama)")
result = run_sandboxed("""\
import socket
try:
    s = socket.create_connection(("127.0.0.1", 11434), timeout=2)
    s.close()
    print("LOCALHOST_OPEN")
except Exception as e:
    print("LOCALHOST_BLOCKED:", e)
""")
show(result)
check("127.0.0.1:11434 (Ollama) unreachable", "LOCALHOST_OPEN" not in result, result)

# ─── Test 8: Filesystem isolation ─────────────────────────────────────────────
header(8, "Filesystem isolation: host paths unreachable")
result = run_sandboxed("""\
import os

# Host-specific paths that must NOT exist inside the container
sensitive = [
    "/Users",
    "/Users/atharv",
    "/Users/atharv/.ssh",
    "/Users/atharv/.ssh/id_rsa",
]
for p in sensitive:
    print(f"  {p}: {os.path.exists(p)}")

# Show container root — should look like a Linux container, not macOS
print("/ contents:", sorted(os.listdir("/")))
print("CWD:", os.getcwd())
""")
show(result)
check("/Users does not exist in container",   "/Users: False" in result, result)
check("/Users/atharv does not exist",         "/Users/atharv: False" in result)
check("/.ssh key not accessible",             "/Users/atharv/.ssh: False" in result)
check("Container has Linux root (/bin, /etc)","'bin'" in result and "'etc'" in result)
check("CWD is /home/sandbox (not project root)", "/home/sandbox" in result, result)

# ─── Test 9: Process isolation ────────────────────────────────────────────────
header(9, "Process isolation: subprocess + PID limit + hostname")
result = run_sandboxed("""\
import subprocess, socket, os

# subprocess.run should work (stays inside container) but with PID limits
try:
    r = subprocess.run(["echo", "inside-container"], capture_output=True, text=True, timeout=3)
    print("subprocess echo:", r.stdout.strip())
except Exception as e:
    print("subprocess blocked:", e)

# Hostname must be the container ID, not the Mac hostname
import socket
print("hostname:", socket.gethostname())

# UID must be 1000 (non-root sandbox user from Dockerfile)
print("uid:", os.getuid())
""")
show(result)
check("subprocess echo works (contained)",    "inside-container" in result, result)
check("UID is 1000 (non-root sandbox user)",  "uid: 1000" in result, result)
# Hostname should be a short hex container ID, not the Mac hostname (e.g. 'MacBook-Pro')
mac_hostname = os.popen("hostname").read().strip()
check("Hostname ≠ Mac hostname",              mac_hostname not in result.split("hostname:")[-1].split("\n")[0],
      f"Mac hostname: '{mac_hostname}'")

# ─── Test 10: No state persistence between runs ───────────────────────────────
header(10, "No state persistence: file written in run 1 is absent in run 2")
result1 = run_sandboxed("open('/tmp/persist_test.txt', 'w').write('hello')\nprint('written')")
result2 = run_sandboxed("""\
import os
print("exists:", os.path.exists("/tmp/persist_test.txt"))
""")
show(result1)
show(result2)
check("Run 1 writes file without error",        "Exit code: 0" in result1)
check("Run 2 sees no file from run 1",          "exists: False" in result2, result2)

# ─── Test 11: Container auto-removed ─────────────────────────────────────────
header(11, "Container auto-removal: --rm flag")
# Run a quick job with a predictable name prefix, then verify it's gone
from sandbox.executor import _docker_binary, _build_docker_env, SANDBOX_IMAGE
import uuid

binary = _docker_binary()
env = _build_docker_env()
cname = f"mrpl-sandbox-test11-{uuid.uuid4().hex[:8]}"

subprocess.run(
    [binary, "run", "--rm", "--name", cname, "--network", "none",
     "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
     "--memory", "256m", "--memory-swap", "256m",
     "--cpus", "1.0", "--pids-limit", "64", "-i",
     SANDBOX_IMAGE, "python3", "-"],
    input=b"print('done')",
    capture_output=True,
    timeout=20,
    env=env,
)
# Now check it's gone from `docker ps -a`
ps = subprocess.run(
    [binary, "ps", "-a", "--filter", f"name={cname}", "--format", "{{.Names}}"],
    capture_output=True, text=True, timeout=5, env=env,
)
container_present = cname in ps.stdout
show(f"docker ps output: '{ps.stdout.strip()}'")
check("Container absent from docker ps -a after run", not container_present,
      f"Found: '{ps.stdout.strip()}'")

# ─── Test 12: Docker-unavailable → no host fallback ──────────────────────────
header(12, "Docker unavailable: must NOT execute code on host")
# Temporarily monkey-patch _docker_available to return False
from sandbox import executor as _exec_module
_orig = _exec_module._docker_available
_exec_module._docker_available = lambda: False

result = run_sandboxed("print('EXECUTED_ON_HOST')")
_exec_module._docker_available = _orig   # restore

show(result)
check("Returns 'Sandbox unavailable' error",  "Sandbox unavailable" in result, result)
check("Code was NOT executed on host",        "EXECUTED_ON_HOST" not in result, result)
check("Error mentions Docker",                "Docker" in result)

# ─── Test 13: Security probes ─────────────────────────────────────────────────
header(13, "Security probes: os.getcwd, os.listdir('/'), hostname")
result = run_sandboxed("""\
import os, socket
print("CWD:", os.getcwd())
print("hostname:", socket.gethostname())
print("uid:", os.getuid())
root_entries = sorted(os.listdir("/"))
print("/ entries:", root_entries)
# These must NOT appear:
for forbidden in ["Users", "System", "Applications", "Library"]:
    if forbidden in root_entries:
        print(f"EXPOSED: {forbidden}")
    else:
        print(f"ISOLATED: {forbidden}")
""")
show(result)
check("CWD is container path",                "/home/sandbox" in result, result)
check("No 'Users' in / (macOS dir exposed)",  "EXPOSED: Users" not in result)
check("No 'Applications' in /",               "EXPOSED: Applications" not in result)
check("UID is 1000 (sandbox user)",           "uid: 1000" in result)

# ─── Summary ─────────────────────────────────────────────────────────────────
total = _passed + _failed + _warned
print(f"\n{BOLD}{'═'*64}{RESET}")
print(f"{BOLD}  RESULTS  {GREEN}{_passed} passed{RESET}{BOLD}"
      f"  {RED}{_failed} failed{RESET}{BOLD}"
      f"  {YELLOW}{_warned} warned{RESET}{BOLD}"
      f"  / {total} total{RESET}")
print(f"{BOLD}{'═'*64}{RESET}")

if _failed > 0:
    print(f"\n{RED}Some tests failed. Review output above.{RESET}")
    sys.exit(1)
elif _warned > 0:
    print(f"\n{YELLOW}All tests passed with warnings. Review warnings above.{RESET}")
else:
    print(f"\n{GREEN}All tests passed. Docker sandbox is operational.{RESET}")
