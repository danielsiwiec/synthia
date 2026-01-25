# syntax=docker/dockerfile:1.4
FROM python:3.13-slim

ARG USER_UID=501
ARG USER_GID=20

SHELL ["/bin/bash", "-c"]

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    (groupadd -g ${USER_GID} synthia 2>/dev/null || groupadd synthia 2>/dev/null || true) && \
    useradd -m -u ${USER_UID} -g ${USER_GID} synthia 2>/dev/null || \
    (useradd -m -u ${USER_UID} synthia && usermod -g ${USER_GID} synthia) && \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian trixie stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin git procps && \
    apt-get purge -y gnupg && apt-get autoremove -y && \
    (groupadd -g 999 docker 2>/dev/null || groupadd -f docker) && \
    usermod -aG docker synthia

RUN pip install uv

WORKDIR /home/synthia/workdir
RUN mkdir -p /home/synthia/.cache && chown -R synthia:synthia /home/synthia

USER synthia

COPY --chown=synthia:synthia pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/home/synthia/.cache/uv,uid=${USER_UID},gid=${USER_GID} \
    uv sync --frozen

COPY --chown=synthia:synthia synthia synthia
COPY --chown=synthia:synthia alembic.ini alembic.ini

RUN mkdir -p ~/.claude ~/.cache /home/synthia/workdir/.claude

CMD ["uv", "run", "uvicorn", "synthia.main:app", "--host", "0.0.0.0", "--port", "8003"]
