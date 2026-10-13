# Read-only redress MCP server over streamable HTTP, for remote clients
# (ChatGPT connectors, claude.ai custom connectors, or a shared team endpoint).
# The case log stays local-only; this image exposes registry lookups only.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE LICENSE-DATA ./
COPY src ./src
COPY registry ./registry
COPY schema ./schema
COPY skills ./skills
RUN pip install --no-cache-dir . && useradd --create-home redress
USER redress
WORKDIR /home/redress
ENV PORT=8765
EXPOSE 8765
CMD ["sh", "-c", "redress serve --transport http --host 0.0.0.0 --port ${PORT} --read-only"]
