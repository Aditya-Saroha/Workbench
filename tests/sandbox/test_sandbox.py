#!/usr/bin/env python3
"""
test_sandbox.py — Manual test suite for sandbox/executor.py

Run from the project root:
    python3 test_sandbox.py

All tests are self-contained — the orchestrator does NOT need to be running.
"""

import sys
import os

# Make sure the project root is on sys.path so 'sandbox' is importable
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sandbox.executor import run_sandboxed

# ─── ANSI colors ──────────────────────────────────────────────────────────────
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
BOLD  = "\033[1m"
RESET = "\033[0m"

def header(n: int, desc: str):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}TEST {n}: {desc}{RESET}")
    print("─"*60)

def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {GREEN}✅ PASS{RESET}  {label}")
    else:
        print(f"  {RED}❌ FAIL{RESET}  {label}")
    if detail:
        print(f"         {YELLOW}{detail}{RESET}")

def show_result(result: str):
    print()
    for line in result.splitlines():
        print(f"  │ {line}")
    print()

passed = 0
failed = 0

# ─── TEST 1: Basic arithmetic ─────────────────────────────────────────────────
header(1, "Basic arithmetic: print(2 + 2)")
result = run_sandboxed("print(2 + 2)")
show_result(result)
ok_exit   = "Exit code: 0" in result
ok_stdout = "4" in result
ok_stderr = "(empty)" in result.split("STDERR:")[-1]
check("Exit code is 0",           ok_exit,   result.split("\n")[0])
check("STDOUT contains '4'",      ok_stdout, result)
check("STDERR is empty",          ok_stderr)
if ok_exit and ok_stdout and ok_stderr: passed += 1
else: failed += 1

# ─── TEST 2: stdlib import ────────────────────────────────────────────────────
header(2, "stdlib import: math.sqrt(144)")
result = run_sandboxed("import math\nprint(math.sqrt(144))")
show_result(result)
ok_exit   = "Exit code: 0" in result
ok_stdout = "12.0" in result
check("Exit code is 0",           ok_exit)
check("STDOUT contains '12.0'",   ok_stdout)
if ok_exit and ok_stdout: passed += 1
else: failed += 1

# ─── TEST 3: Runtime exception ────────────────────────────────────────────────
header(3, "Runtime exception: raise ValueError('test error')")
result = run_sandboxed("raise ValueError('test error')")
show_result(result)
ok_exit   = "Exit code: 1" in result
ok_stderr = "ValueError" in result and "test error" in result
ok_stdout = "(empty)" in result.split("STDERR:")[0].split("STDOUT:")[-1]
check("Exit code is 1",            ok_exit)
check("STDERR contains ValueError", ok_stderr)
check("STDOUT is empty",            ok_stdout)
if ok_exit and ok_stderr: passed += 1
else: failed += 1

# ─── TEST 4: Infinite loop → timeout ─────────────────────────────────────────
header(4, "Infinite loop → timeout after 10 s  (this WILL take 10 s)")
result = run_sandboxed("while True:\n    pass")
show_result(result)
ok_timeout = "timed out" in result.lower() and "10 seconds" in result
check("Execution timed out cleanly", ok_timeout)
check("No crash / exception leaked",  "Error: Sandbox execution failed" not in result or ok_timeout)
if ok_timeout: passed += 1
else: failed += 1

# ─── TEST 5: Output truncation ────────────────────────────────────────────────
header(5, "Output bomb: print('A' * 2_000_000)")
result = run_sandboxed("print('A' * 2_000_000)")
show_result(result[:400] + "\n  ...(result truncated for display)..." if len(result) > 400 else result)
ok_trunc = "truncated" in result.lower()
ok_limit  = len(result.encode()) <= 1 * 1024 * 1024 + 500   # allow small overhead
check("Output marked as truncated", ok_trunc)
check("Result string ≤ ~1 MB",      ok_limit, f"actual: {len(result.encode())} bytes")
if ok_trunc and ok_limit: passed += 1
else: failed += 1

# ─── TEST 6: Sensitive file access (read) ─────────────────────────────────────
header(6, "Sensitive file: attempt to read ~/.ssh/id_rsa")
code = textwrap.dedent("""\
    try:
        with open(os.path.expanduser('~/.ssh/id_rsa')) as f:
            print('READ SUCCESS:', f.read()[:20])
    except Exception as e:
        print('BLOCKED:', e)
""")
# Need os imported in the code
code = "import os\n" + code
result = run_sandboxed(code)
show_result(result)
# In fallback mode (no Seatbelt) the HOME is redirected to tmpdir, so
# os.path.expanduser('~') returns the tmpdir, not the real home.
ok_blocked = "READ SUCCESS" not in result
check("SSH key NOT read successfully", ok_blocked,
      "In Seatbelt mode: file-read denied. "
      "In fallback mode: HOME→tmpdir so ~/.ssh doesn't resolve to real home.")
if ok_blocked: passed += 1
else: failed += 1

# ─── TEST 7: Network request attempt ─────────────────────────────────────────
header(7, "Network: attempt HTTP request to example.com")
import sys as _sys  # noqa — already imported
code = textwrap.dedent("""\
    import socket
    try:
        s = socket.create_connection(('example.com', 80), timeout=3)
        s.close()
        print('NETWORK SUCCESS')
    except Exception as e:
        print('NETWORK BLOCKED:', e)
""")
result = run_sandboxed(code)
show_result(result)
ok_net = "NETWORK SUCCESS" not in result
check("Network connection NOT successful", ok_net,
      "In Seatbelt mode: network* denied. "
      "In fallback mode: network may succeed — Docker required for enforcement.")
if ok_net: passed += 1
else:
    print(f"  {YELLOW}ℹ️  NOTE: Network was NOT blocked. This is expected in fallback "
          f"mode (no Seatbelt). A container is required for production.{RESET}")
    failed += 1

# ─── TEST 8: Subprocess creation attempt ─────────────────────────────────────
header(8, "Subprocess: attempt os.system('echo spawned')")
code = textwrap.dedent("""\
    import os, subprocess
    try:
        r = subprocess.run(['echo', 'spawned'], capture_output=True, text=True)
        print('SUBPROCESS SUCCESS:', r.stdout.strip())
    except Exception as e:
        print('SUBPROCESS BLOCKED:', e)
    try:
        ret = os.system('echo direct_system')
        print('OS_SYSTEM RET:', ret)
    except Exception as e:
        print('OS_SYSTEM BLOCKED:', e)
""")
result = run_sandboxed(code)
show_result(result)
ok_blocked = "SUBPROCESS SUCCESS" not in result or "SUBPROCESS BLOCKED" in result
check("subprocess.run() blocked by RLIMIT_NPROC", ok_blocked)
if ok_blocked: passed += 1
else:
    print(f"  {YELLOW}ℹ️  If SUBPROCESS SUCCESS appears, RLIMIT_NPROC may not have "
          f"taken effect. Check kernel/macOS version.{RESET}")
    failed += 1

# ─── TEST 9: Empty code input validation ─────────────────────────────────────
header(9, "Input validation: empty string")
result = run_sandboxed("   ")
show_result(result)
ok = "no code" in result.lower() or "error" in result.lower()
check("Empty code returns error message", ok)
if ok: passed += 1
else: failed += 1

# ─── TEST 10: Non-string input validation ─────────────────────────────────────
header(10, "Input validation: non-string (None)")
result = run_sandboxed(None)   # type: ignore
show_result(result)
ok = "error" in result.lower()
check("None input returns error message", ok)
if ok: passed += 1
else: failed += 1

# ─── Summary ─────────────────────────────────────────────────────────────────
total = passed + failed
print(f"\n{'═'*60}")
print(f"{BOLD}RESULTS: {GREEN}{passed}{RESET}{BOLD}/{total} passed{RESET}   "
      f"{RED}{failed} failed{RESET}")
print("═"*60)
if failed:
    print(f"\n{YELLOW}Note: Some failures may be expected in fallback mode "
          f"(no macOS Seatbelt).\nSee SECURITY LIMITATIONS in sandbox/executor.py.{RESET}\n")

import textwrap  # noqa — needed for test 6; imported here to avoid circular at top
