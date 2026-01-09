FROM python:3.13-slim

ARG USER_UID=501
ARG USER_GID=20

SHELL ["/bin/bash", "-c"]

RUN (groupadd -g ${USER_GID} synthia 2>/dev/null || groupadd synthia 2>/dev/null || true) && \
    useradd -m -u ${USER_UID} -g ${USER_GID} synthia 2>/dev/null || \
    (useradd -m -u ${USER_UID} synthia && usermod -g ${USER_GID} synthia) && \
    apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    chmod a+r /etc/apt/keyrings/docker.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian trixie stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    apt-get purge -y gnupg && apt-get autoremove -y && \
    (groupadd -g 999 docker 2>/dev/null || groupadd -f docker) && \
    usermod -aG docker synthia && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /home/synthia/workdir

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY synthia synthia
COPY --chmod=755 scripts/init-plugins.sh /usr/local/bin/init-plugins.sh

RUN chown -R synthia:synthia /home/synthia

USER synthia

RUN curl -fsSL https://claude.ai/install.sh | bash && \
    mkdir -p ~/.claude /home/synthia/workdir/.claude

ENTRYPOINT ["/usr/local/bin/init-plugins.sh"]
CMD ["uv", "run", "uvicorn", "synthia.main:app", "--host", "0.0.0.0", "--port", "8003"]
