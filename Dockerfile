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
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin nodejs git && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get purge -y gnupg && apt-get autoremove -y && \
    (groupadd -g 999 docker 2>/dev/null || groupadd -f docker) && \
    usermod -aG docker synthia && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /home/synthia/workdir

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY synthia synthia

# Install plugin using secret mount - copy to writable location since claude CLI writes to it
RUN --mount=type=secret,id=claude_credentials,target=/run/secrets/claude.json \
    cp /run/secrets/claude.json /root/.claude.json && \
    claude plugin marketplace add danielsiwiec/episodic-memory && \
    claude plugin install episodic-memory@episodic-memory-dev && \
    rm /root/.claude.json && \
    PLUGIN_DIR=$(find /root/.claude/plugins/cache -path "*/episodic-memory/*/cli" -type d 2>/dev/null | head -1 | xargs dirname) && \
    cd "$PLUGIN_DIR" && npm install && \
    mkdir -p /home/synthia/.claude && \
    mv /root/.claude/plugins /home/synthia/.claude/plugins

RUN chown -R synthia:synthia /home/synthia

USER synthia

ENV PATH="/home/synthia/.local/bin:$PATH"

RUN mkdir -p ~/.claude /home/synthia/workdir/.claude /home/synthia/.local/bin && \
    CLI_PATH=$(find /home/synthia/.claude/plugins/cache -path "*/episodic-memory/*/cli/episodic-memory" -type f 2>/dev/null | head -1) && \
    ln -sf "$CLI_PATH" /home/synthia/.local/bin/episodic-memory
CMD ["uv", "run", "uvicorn", "synthia.main:app", "--host", "0.0.0.0", "--port", "8003"]
