import asyncio
import json
from orchestrator.tools import execute_tool
from orchestrator.agent import generate_plan, PlanStep

def test_phase3():
    print("--- Phase 3 Tool Hardening Tests ---")
    
    # A. Valid tool: python_sandbox
    print("\nA. Valid Tool: python_sandbox")
    res = execute_tool("python_sandbox", {"code": "print(2+2)"})
    print("Output:", res.split('\n')[0], "...")
    assert "Exit code: 0" in res

    # B. Unknown tool
    print("\nB. Unknown tool")
    res = execute_tool("fake_tool", {})
    print("Output:", res)
    assert "Error: Unknown tool: fake_tool" in res

    # C/D/E/F. Argument validation for python_sandbox
    print("\nC/D. Missing args for python_sandbox")
    res = execute_tool("python_sandbox", {})
    print("Output:", res)
    assert "Error: Missing 'code' argument" in res

    print("\nE. Code is integer")
    res = execute_tool("python_sandbox", {"code": 123})
    print("Output:", res)
    assert "Error: 'code' argument must be a string" in res

    print("\nF. Empty code")
    res = execute_tool("python_sandbox", {"code": "   "})
    print("Output:", res)
    assert "Error: 'code' argument cannot be empty" in res

    # G. Shell-injection-looking string
    print("\nG. Shell injection string as code")
    res = execute_tool("python_sandbox", {"code": 'import os; print("Executed")'})
    print("Output:", res.split('\n')[0], "...")
    # It just runs in Python inside docker, not a host shell.
    assert "Exit code: 0" in res

    # J. Malformed JSON handled correctly (if we test via execute_tool direct)
    print("\nJ. Non-dict arguments")
    res = execute_tool("python_sandbox", "not a dict")
    print("Output:", res)
    assert "Error: tool_args must be a dictionary" in res

    print("\n--- All Phase 3 Execution Tests Passed ---")

if __name__ == "__main__":
    test_phase3()
