# sandbox/README.md
# Python Sandbox — MRPL AI Workbench

## Why the Sandbox Exists

The MRPL Agentic Workbench uses a local LLM to generate multi-step plans. One of the available tools, `python_sandbox`, lets the agent execute Python code as part of a task. LLM-generated code is **untrusted by default**. Without isolation, executing that code directly inside the orchestrator process would allow:

- Reading or deleting project files, credentials, or SSH keys
- Making network requests (data exfiltration, external API calls)
- Consuming unlimited CPU/memory
- Crashing the orchestrator with an unhandled exception
- Spawning persistent background processes

The sandbox isolates every execution inside a fresh Docker container so none of the above is possible.

---

## Architecture

```
User Prompt
    │
    ▼
orchestrator/agent.py  (generates plan via LLM)
    │
    ▼
orchestrator/tools.py  execute_tool("python_sandbox", {"code": "..."})
    │
    ▼
sandbox/executor.py    run_sandboxed(code)
    │
    ▼  docker run [security flags] mrpl-sandbox:latest
    │
    ├─ code piped via stdin → python3 -
    │
    ▼  stdout / stderr captured
    │
    ▼
formatted result string returned to Agent Critic
```

### Key design decisions

| Decision | Reason |
|---|---|
| Code piped via **stdin** | No host filesystem needs to be mounted; cleanest isolation |
| **Named container** per execution | Allows reliable `docker stop <name>` on timeout |
| **`--rm`** always | Containers are ephemeral; no state leaks between runs |
| **Auto-build** if image missing | Zero-friction setup for developers |
| **No fallback to host execution** | Security > convenience; untrusted code never runs on host |

---

## Docker Isolation

### Network isolation

```
--network none
```

The container has **no network interfaces** except loopback. This means:

- No DNS resolution → `socket.getaddrinfo("example.com", ...)` fails
- No outbound connections → cannot reach the Internet
- No connections to host services → Ollama (11434), orchestrator (8001), RAG server (8081) are all unreachable from inside the container
- Loopback (`127.0.0.1`) inside the container is the container's own loopback — it does not connect to host `localhost`

### Filesystem isolation

No host directories are mounted into the container. The container gets its own root filesystem derived from `python:3.13-slim`:

```
Container /
├── bin, etc, lib, usr  ← standard Linux directories
└── home/sandbox        ← writable home for UID 1000

Host / (macOS)
├── Users/              ← NOT visible inside container
├── Applications/       ← NOT visible inside container
└── ...                 ← NOT visible inside container
```

The container's filesystem is **ephemeral** — it is destroyed when the container exits (`--rm`).

### Capability and privilege isolation

```
--cap-drop ALL
--security-opt no-new-privileges
```

All Linux capabilities are dropped. This prevents:
- `CAP_NET_RAW` — raw socket access
- `CAP_SYS_ADMIN` — mounting filesystems, changing namespaces
- `CAP_PTRACE` — debugging/tracing other processes
- `CAP_SETUID` / `CAP_SETGID` — privilege escalation via setuid binaries
- All other capabilities

`no-new-privileges` additionally prevents any process inside the container from gaining capabilities via `execve` (e.g. setuid binaries).

---

## Resource Limits

| Resource | Limit | Flag |
|---|---|---|
| Memory | 256 MB | `--memory 256m` |
| Swap | 0 (disabled) | `--memory-swap 256m` (same = no swap) |
| CPU | 1.0 core | `--cpus 1.0` |
| Processes/threads | 64 | `--pids-limit 64` |
| Wall-clock time | 10 seconds | `communicate(timeout=10)` |
| Output size | 1 MB per stream | enforced in `executor.py` |

These limits are calibrated for a development laptop running multiple services simultaneously. They are intentionally not tight enough to break normal numerical computation.

---

## Non-Root User

The Dockerfile creates `UID 1000 / username: sandbox`:

```dockerfile
RUN useradd --uid 1000 --gid users sandbox
USER sandbox
WORKDIR /home/sandbox
```

Execution inside the container runs as this non-root user, providing an additional layer of protection even if a capability is accidentally left enabled.

---

## Timeout

The orchestrator calls `subprocess.communicate(timeout=10)`. On expiry:

1. `docker stop --time 3 <container-name>` — sends `SIGTERM`, waits 3 s, then `SIGKILL`
2. The container's `--rm` flag ensures it is removed
3. The docker client subprocess is killed
4. `run_sandboxed()` returns `"Error: Execution timed out after 10 seconds. Container was stopped and removed."`

---

## Output Limit

`stdout` and `stderr` are each capped at **1 MB**. If output exceeds the limit it is truncated and a marker is appended:

```
[... STDOUT truncated: output exceeded 1 MB limit ...]
```

This protects the orchestrator from buffering enormous outputs from a misbehaving program.

---

## How to Build the Sandbox Image

Build once from the project root:

```bash
docker build -t mrpl-sandbox:latest sandbox/
```

The image is cached locally. The executor checks for it on first use and auto-builds if missing.

To rebuild from scratch (e.g. after modifying the Dockerfile):

```bash
docker build --no-cache -t mrpl-sandbox:latest sandbox/
```

To verify the image:

```bash
docker image inspect mrpl-sandbox:latest
```

---

## How to Run Tests

```bash
# From the project root — Docker daemon must be running
python3 test_sandbox_docker.py
```

Tests covered:

1. Basic computation (`print(2 + 2)`)
2. Math stdlib import (`math.sqrt`)
3. Python exception (exit code 1, traceback)
4. Infinite loop → timeout (10 s)
5. Large output → truncated at 1 MB
6. Network isolation (external host blocked)
7. Localhost isolation (Ollama port blocked)
8. Filesystem isolation (`/Users`, `~/.ssh` absent)
9. Process isolation (subprocess works but stays contained, UID=1000)
10. No state persistence between runs
11. Container auto-removal (`--rm` verified via `docker ps -a`)
12. Docker-unavailable guard (no host fallback)
13. Security probes (`os.getcwd`, `os.listdir('/')`, hostname)

---

## Docker-Unavailable Behaviour

If Docker Desktop is not running or the daemon socket is unreachable:

```
Sandbox unavailable: Docker runtime is not reachable.
Please ensure Docker Desktop is running and try again.
Code was NOT executed on the host.
Falling back to host execution is intentionally disabled.
```

**The sandbox never silently falls back to executing untrusted code on the host.**

---

## Security Limitations (Honest Assessment)

The sandbox provides **container-level isolation**, not a full hypervisor or hardware-enforced boundary. Known limitations:

| Risk | Status |
|---|---|
| **Shared kernel** | Docker on macOS uses a Linux VM (Docker Desktop), so user code runs in that VM's Linux kernel, not directly on the macOS kernel. This is stronger than Linux Docker on bare metal but weaker than a per-workload VM. |
| **No seccomp profile** | Dangerous Linux syscalls (`ptrace`, `mount`, etc.) are not explicitly blocked. `--cap-drop ALL` prevents most abuse but a seccomp profile would add defence-in-depth. |
| **Root inside container** | UID 0 inside a container namespace retains some intra-container privileges. The Dockerfile uses UID 1000, mitigating this. |
| **No read-only root fs** | Code can write inside the container's ephemeral filesystem. Files vanish on `--rm` but exist during execution. Add `--read-only --tmpfs /tmp` to harden further. |
| **Output buffered in host RAM** | All stdout/stderr is buffered by the Python `subprocess.communicate()` call before the 1 MB cap is applied. The container's 256 MB memory limit bounds this in practice. |

### Roadmap for production hardening

- Add a **seccomp profile** (deny `ptrace`, `mount`, `syslog`, etc.)
- Add `--read-only --tmpfs /tmp --tmpfs /home/sandbox` to prevent in-container writes
- Use **gVisor (`--runtime=runsc`)** or **Kata Containers** for per-container kernel isolation
- Run the orchestrator service as a dedicated non-root host user
- Add image signing and digest pinning for the base `python:3.13-slim` image
