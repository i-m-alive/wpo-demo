# One image for every wpo-reference service (stand-ins, MCP servers, agents); docker-compose.yml picks the command.
# Runs as a non-root user and writes nothing at run time, so it also runs under a read-only file system.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY stubs/ stubs/
COPY mcp_servers/ mcp_servers/
COPY agents/ agents/

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin wpo
USER 10001
