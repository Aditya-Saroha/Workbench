"""
sandbox/executor.py — Docker-based Python sandbox for the MRPL AI Workbench.

Phase 2: Docker is the PRIMARY and ONLY security boundary.

Architecture
------------
Agent
  → tools.py:execute_tool("python_sandbox", {"code": "..."})
    → run_sandboxed(code)
      → docker run [security flags] mrpl-sandbox:latest
          code piped via stdin → python3 -
            stdout / stderr captured
      → formatted result string returned to Agent

Security Model
--------------
Every execution creates a fresh, ephemeral Docker container that:

  ✅ Has NO network access            (--network none)
  ✅ Has NO host filesystem mounts    (nothing mounted into container)
  ✅ Has NO Linux capabilities        (--cap-drop ALL)
  ✅ Cannot escalate privileges       (--security-opt no-new-privileges)
  ✅ Runs as non-root UID 1000        (USER sandbox in Dockerfile)
  ✅ Is auto-removed on exit          (--rm)
  ✅ Has a hard memory ceiling        (--memory 256m, --memory-swap 256m)
  ✅ Has a CPU share limit            (--cpus 1.0)
  ✅ Has a PID limit (anti-fork-bomb) (--pids-limit 64)
  ✅ Has a wall-clock timeout         (10 seconds; container stopped on expiry)
  ✅ stdout/stderr capped at 1 MB     (orchestrator safe from output floods)
  ✅ Minimal environment              (no API keys, tokens, or project paths)

Docker socket discovery
-----------------------
Docker Desktop on macOS places its socket at:
    ~/.docker/run/docker.sock

This module discovers the socket path automatically in priority order:
    1. DOCKER_HOST environment variable (user override)
    2. ~/.docker/run/docker.sock        (Docker Desktop macOS default)
    3. /var/run/docker.sock             (Linux / OrbStack / standard)

DOCKER_CONFIG is set to a clean temporary directory so the Docker CLI
does not attempt to read credentials via the "docker-credential-desktop"
helper — which is NOT on PATH in this project's virtualenv.

Docker-unavailable behaviour
----------------------------
If Docker is not available or the sandbox image cannot be built,
run_sandboxed() returns a clear error string.

⚠️  It does NOT silently fall back to executing untrusted code on the host.
    Security is more important than convenience.

Public API
----------
    run_sandboxed(code: str) -> str
    build_sandbox_image() -> tuple[bool, str]
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Tunables ────────────────────────────────────────────────────────────────

SANDBOX_IMAGE      = "mrpl-sandbox:latest"
TIMEOUT_SECONDS    = 10       # Wall-clock kill threshold for container execution
MAX_OUTPUT_BYTES   = 1 * 1024 * 1024   # 1 MB per stream (stdout / stderr)
DOCKER_MEMORY      = "256m"   # Hard RAM ceiling (--memory)
DOCKER_CPUS        = "1.0"    # CPU core share (--cpus)
DOCKER_PIDS_LIMIT  = 64       # Max OS-level processes inside container (--pids-limit)
DOCKER_STOP_TIMEOUT = 3       # Seconds for graceful stop before SIGKILL


# ─── Docker discovery ────────────────────────────────────────────────────────

def _docker_binary() -> Optional[str]:
    """
    Return the path to the docker binary.

    Checks common non-PATH locations for Docker Desktop on macOS
    in addition to the system PATH.
    """
    # System PATH first
    path = shutil.which("docker")
    if path:
        return path

    # Docker Desktop on macOS installs here but may not be on PATH
    macos_path = "/Applications/Docker.app/Contents/Resources/bin/docker"
    if os.path.isfile(macos_path):
        return macos_path

    return None


def _docker_socket() -> Optional[str]:
    """
    Return the Docker socket URI to use, or None if no socket is found.

    Priority:
      1. DOCKER_HOST env variable (user override)
      2. ~/.docker/run/docker.sock  (Docker Desktop macOS)
      3. /var/run/docker.sock       (Linux / OrbStack)
    """
    env_host = os.environ.get("DOCKER_HOST", "")
    if env_host:
        return env_host

    macos_sock = os.path.expanduser("~/.docker/run/docker.sock")
    if os.path.exists(macos_sock):
        return f"unix://{macos_sock}"

    linux_sock = "/var/run/docker.sock"
    if os.path.exists(linux_sock):
        return f"unix://{linux_sock}"

    return None


def _build_docker_env() -> dict[str, str]:
    """
    Build a clean environment dict for subprocess Docker calls.

    Sets DOCKER_HOST to the discovered socket and DOCKER_CONFIG to a
    temporary empty directory to bypass the docker-credential-desktop
    helper (which is not on PATH in this project's venv and would cause
    the docker CLI to abort with a credentials error).
    """
    env = os.environ.copy()

    socket_uri = _docker_socket()
    if socket_uri:
        env["DOCKER_HOST"] = socket_uri

    # Point DOCKER_CONFIG at a clean dir with an empty config so the CLI
    # skips the credential store helper entirely.
    clean_cfg = Path(tempfile.gettempdir()) / "mrpl_docker_cfg"
    clean_cfg.mkdir(exist_ok=True)
    cfg_file = clean_cfg / "config.json"
    if not cfg_file.exists():
        cfg_file.write_text("{}\n")
    env["DOCKER_CONFIG"] = str(clean_cfg)

    return env


# ─── Docker availability probes ──────────────────────────────────────────────

def _docker_available() -> bool:
    """
    Return True only if the Docker binary exists AND the daemon is reachable.
    """
    binary = _docker_binary()
    if not binary:
        return False

    try:
        result = subprocess.run(
            [binary, "info"],
            capture_output=True,
            timeout=10,
            env=_build_docker_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _image_exists() -> bool:
    """Return True if the sandbox image is present in the local image store."""
    binary = _docker_binary()
    if not binary:
        return False
    try:
        result = subprocess.run(
            [binary, "image", "inspect", SANDBOX_IMAGE],
            capture_output=True,
            timeout=10,
            env=_build_docker_env(),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


# ─── Image management ────────────────────────────────────────────────────────

def build_sandbox_image() -> tuple[bool, str]:
    """
    Build the mrpl-sandbox Docker image from sandbox/Dockerfile.

    This is called automatically by run_sandboxed() when the image is
    missing. It may also be called manually during setup.

    Returns:
        (success: bool, message: str)
    """
    binary = _docker_binary()
    if not binary:
        return False, "Docker binary not found."

    dockerfile_dir = Path(__file__).parent
    dockerfile = dockerfile_dir / "Dockerfile"
    if not dockerfile.exists():
        return False, f"Dockerfile not found at {dockerfile}."

    logger.info(
        "Building sandbox image '%s' from %s (may take 1-2 minutes)...",
        SANDBOX_IMAGE, dockerfile_dir,
    )

    result = subprocess.run(
        [binary, "build", "-t", SANDBOX_IMAGE, "-f", str(dockerfile), str(dockerfile_dir)],
        capture_output=True,
        text=True,
        timeout=300,   # 5 minutes max
        env=_build_docker_env(),
    )

    if result.returncode == 0:
        logger.info("Sandbox image '%s' built successfully.", SANDBOX_IMAGE)
        return True, "Image built successfully."
    else:
        return False, result.stderr.strip()


def _ensure_image() -> tuple[bool, str]:
    """
    Guarantee the sandbox image is available.

    If missing: attempts to auto-build it.
    Returns (available: bool, error_message: str).
    """
    if _image_exists():
        return True, ""

    logger.warning(
        "Sandbox image '%s' not found in local store. Auto-building now...",
        SANDBOX_IMAGE,
    )
    success, msg = build_sandbox_image()
    if success:
        return True, ""
    return False, f"Could not build sandbox image: {msg}"


# ─── Output helpers ──────────────────────────────────────────────────────────

def _decode_and_cap(data: bytes, stream_name: str) -> str:
    """
    Decode bytes to str, hard-cap at MAX_OUTPUT_BYTES, and annotate if
    truncation occurred.
    """
    truncated = len(data) > MAX_OUTPUT_BYTES
    text = data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if truncated:
        text += (
            f"\n\n[... {stream_name} truncated: "
            f"output exceeded {MAX_OUTPUT_BYTES // 1024 // 1024} MB limit ...]"
        )
    return text


def _format_result(exit_code: int, stdout: str, stderr: str) -> str:
    """Format execution output into the standard agent-readable string."""
    parts = [f"Exit code: {exit_code}", ""]
    parts.append("STDOUT:")
    parts.append(stdout.rstrip() if stdout.strip() else "(empty)")
    parts.append("")
    parts.append("STDERR:")
    parts.append(stderr.rstrip() if stderr.strip() else "(empty)")
    return "\n".join(parts)


# ─── Public function ─────────────────────────────────────────────────────────

def run_sandboxed(code: str) -> str:
    """
    Execute Python code inside a fresh Docker container and return the result.

    The code is NEVER exec()/eval()'d inside the orchestrator process.
    Execution is fully contained within a one-shot Docker container that
    is automatically removed on exit.

    Security guarantees provided by Docker:
      - No network (--network none)
      - No host filesystem mounts
      - Dropped all Linux capabilities (--cap-drop ALL)
      - No privilege escalation (--security-opt no-new-privileges)
      - Non-root user (UID 1000, defined in Dockerfile)
      - Memory hard limit: 256 MB
      - CPU share limit: 1.0 core
      - PID limit: 64 (prevents fork bombs)
      - Auto-removed on exit (--rm)
      - Hard wall-clock timeout: 10 seconds

    Args:
        code: Python source code string (from the agent / LLM).

    Returns:
        A formatted string with exit code, STDOUT, and STDERR.
        On timeout: "Error: Execution timed out after 10 seconds."
        On Docker unavailable: error string, code is NOT executed on host.

    Example (success)::

        Exit code: 0
        STDOUT:
        4
        STDERR:
        (empty)

    Example (error)::

        Exit code: 1
        STDOUT:
        (empty)
        STDERR:
        Traceback ...
        ValueError: test error
    """
    # ── Input validation ─────────────────────────────────────────────────────
    if not isinstance(code, str):
        return "Error: 'code' argument must be a string."
    code = code.strip()
    if not code:
        return "Error: No code provided to python_sandbox."

    # ── Docker availability check ─────────────────────────────────────────────
    # SECURITY INVARIANT: never execute code on the host if Docker is down.
    if not _docker_available():
        return (
            "Sandbox unavailable: Docker runtime is not reachable. "
            "Please ensure Docker Desktop is running and try again.\n"
            "Code was NOT executed on the host. "
            "Falling back to host execution is intentionally disabled."
        )

    # ── Image availability ────────────────────────────────────────────────────
    image_ok, image_err = _ensure_image()
    if not image_ok:
        return (
            f"Sandbox unavailable: {image_err}\n"
            f"To build manually: docker build -t {SANDBOX_IMAGE} sandbox/\n"
            "Code was NOT executed on the host."
        )

    binary = _docker_binary()
    # Unique container name allows reliable targeted stop on timeout
    container_name = f"mrpl-sandbox-{uuid.uuid4().hex[:12]}"
    docker_env = _build_docker_env()

    # ── Docker command ────────────────────────────────────────────────────────
    # Flags explained:
    #   --rm                          auto-remove container on exit
    #   --name <uuid>                 reliable handle for timeout cleanup
    #   --network none                no outbound or inbound network
    #   --cap-drop ALL                drop every Linux capability
    #   --security-opt no-new-privileges  block setuid/setgid escalation
    #   --memory 256m                 hard RAM ceiling
    #   --memory-swap 256m            == memory → no swap allowed
    #   --cpus 1.0                    CPU core share
    #   --pids-limit 64               prevent fork/thread bombs
    #   -i                            keep stdin open (code piped in)
    cmd = [
        binary, "run",
        "--rm",
        "--name", container_name,
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--memory", DOCKER_MEMORY,
        "--memory-swap", DOCKER_MEMORY,   # same value = no swap
        "--cpus", DOCKER_CPUS,
        "--pids-limit", str(DOCKER_PIDS_LIMIT),
        "-i",                             # keep stdin open
        SANDBOX_IMAGE,
        # Override CMD if image CMD differs; this is explicit:
        "python3", "-",                   # read code from stdin
    ]

    import threading

    def _read_bounded(pipe, max_bytes: int) -> tuple[bytes, bool]:
        """Read up to max_bytes from a pipe. Returns (captured_bytes, truncated_flag)."""
        captured = bytearray()
        truncated = False
        try:
            while True:
                chunk = pipe.read(8192)
                if not chunk:
                    break
                if not truncated:
                    space = max_bytes - len(captured)
                    if space > 0:
                        captured.extend(chunk[:space])
                    if len(chunk) > space:
                        truncated = True
                        break  # Stop reading to bound host processing and block writer
        except Exception:
            pass
        finally:
            try:
                pipe.close() # Force close to signal broken pipe to producer
            except Exception:
                pass
        return bytes(captured), truncated

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=docker_env,
        )

        # ── Write code to stdin ───────────────────────────────────────────────
        try:
            proc.stdin.write(code.encode("utf-8"))
            proc.stdin.close()
        except OSError:
            pass  # Container might have died before we finished writing

        # ── Read streams concurrently to avoid deadlocks ──────────────────────
        out_data = {"bytes": b"", "truncated": False}
        err_data = {"bytes": b"", "truncated": False}

        def consume_out():
            b, t = _read_bounded(proc.stdout, MAX_OUTPUT_BYTES)
            out_data["bytes"] = b
            out_data["truncated"] = t

        def consume_err():
            b, t = _read_bounded(proc.stderr, MAX_OUTPUT_BYTES)
            err_data["bytes"] = b
            err_data["truncated"] = t

        t_out = threading.Thread(target=consume_out)
        t_err = threading.Thread(target=consume_err)
        t_out.start()
        t_err.start()

        # ── Wait with hard timeout ────────────────────────────────────────────
        try:
            proc.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            # 1. Stop the container gracefully (sends SIGTERM, then SIGKILL)
            #    This is the clean path: container exits, --rm removes it.
            subprocess.run(
                [binary, "stop", "--time", str(DOCKER_STOP_TIMEOUT), container_name],
                capture_output=True,
                timeout=DOCKER_STOP_TIMEOUT + 5,
                env=docker_env,
            )
            # 2. Kill the docker-client subprocess (it's blocking on comms)
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            
            t_out.join(timeout=1)
            t_err.join(timeout=1)
            
            return (
                f"Error: Execution timed out after {TIMEOUT_SECONDS} seconds. "
                "Container was stopped and removed."
            )

        t_out.join(timeout=1)
        t_err.join(timeout=1)

        # ── Decode and enforce output size cap ────────────────────────────────
        def decode_and_mark(d: dict, name: str) -> str:
            text = d["bytes"].decode("utf-8", errors="replace")
            if d["truncated"]:
                text += (
                    f"\n\n[... {name} truncated: "
                    f"output exceeded {MAX_OUTPUT_BYTES // 1024 // 1024} MB limit ...]"
                )
            return text

        stdout_text = decode_and_mark(out_data, "STDOUT")
        stderr_text = decode_and_mark(err_data, "STDERR")

        return _format_result(proc.returncode, stdout_text, stderr_text)

    except Exception as exc:
        logger.exception("Sandbox infrastructure error (container: %s)", container_name)
        # Emergency forced removal in case --rm didn't fire
        try:
            subprocess.run(
                [binary, "rm", "-f", container_name],
                capture_output=True,
                timeout=5,
                env=docker_env,
            )
        except Exception:
            pass
        return f"Error: Sandbox execution failed unexpectedly: {exc}"


# ─── SECURITY LIMITATIONS (honest assessment) ────────────────────────────────
#
# What Docker provides for this sandbox:
#   ✅ Kernel namespace isolation (pid, net, mnt, uts, ipc, user)
#   ✅ Network namespace: --network none = no interfaces except loopback
#      (loopback is inside the container — cannot reach host ports)
#   ✅ Filesystem: no host paths mounted; container has its own root
#   ✅ Capability drop: ALL capabilities removed, no raw sockets/chroot/etc.
#   ✅ No privilege escalation via setuid binaries
#   ✅ Memory/CPU/PID limits enforced by cgroups
#
# What this sandbox does NOT currently provide:
#   ⚠️  No seccomp profile: dangerous syscalls (ptrace, etc.) are not blocked
#      → Add --security-opt seccomp=sandbox/seccomp.json for hardening
#   ⚠️  Root inside container: even with --cap-drop ALL, UID 0 inside the
#      container namespace has some elevated privileges within that ns.
#      The Dockerfile creates UID 1000, but the CMD in python:3.13-slim base
#      may still run as root if not using our custom image.
#      → Always use the mrpl-sandbox image (not python:3.13-slim directly)
#   ⚠️  No read-only root filesystem: code can write anywhere inside the
#      ephemeral container. Files vanish on --rm but exist during execution.
#      → Add --read-only --tmpfs /tmp for stronger posture
#   ⚠️  No resource.io limits: large amounts of I/O could slow the host
#   ⚠️  Not a VM: kernel is shared with the host (Docker Desktop uses a Linux VM
#      on macOS, which adds another isolation layer, but it is not a hypervisor
#      per-container boundary)
#
# For production (government workbench):
#   → Add a seccomp profile
#   → Add --read-only --tmpfs /tmp --tmpfs /home/sandbox
#   → Consider gVisor (runsc) or Kata Containers for stronger kernel isolation
#   → Run the orchestrator service as a non-root host user
