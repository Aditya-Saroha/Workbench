# sandbox/Dockerfile
#
# Minimal Python execution sandbox for the MRPL AI Workbench.
#
# PURPOSE
# -------
# This image runs LLM-generated Python code in a kernel-isolated container.
# It deliberately contains ONLY the Python interpreter and its standard
# library. No project files, secrets, credentials, or user data are ever
# present inside this image or the containers it creates.
#
# WHAT THIS IMAGE INTENTIONALLY LACKS
# ------------------------------------
#   • No pip packages beyond stdlib (network is off at runtime anyway)
#   • No project source code
#   • No API keys or environment secrets
#   • No access to /Users, ~/.ssh, /home/<host-user>, or any host path
#   • No writable root filesystem at runtime (--read-only can be added)
#
# BUILDING
# --------
#   From the project root:
#       docker build -t mrpl-sandbox:latest sandbox/
#
# This image is built once. The executor pulls it from the local image store
# for every execution — it does NOT rebuild on every agent invocation.

FROM python:3.13-slim

LABEL org.opencontainers.image.title="mrpl-sandbox"
LABEL org.opencontainers.image.description="Isolated Python execution environment — MRPL AI Workbench"
LABEL org.opencontainers.image.version="2.0"

# Create a dedicated non-root user for code execution.
# Fixed UID 1000 makes the image reproducible and avoids root-related risks.
RUN useradd \
        --create-home \
        --shell /bin/bash \
        --uid 1000 \
        --gid users \
        sandbox

# Safe working directory — no project content here.
# The container CWD is /home/sandbox, not the orchestrator or RAG root.
WORKDIR /home/sandbox

# Drop to non-root before any CMD or ENTRYPOINT.
# Combine with --cap-drop ALL at runtime for defence-in-depth.
USER sandbox

# Read Python source from stdin and execute it.
# python3 - : reads from stdin, behaves like python3 < script.py
CMD ["python3", "-"]
