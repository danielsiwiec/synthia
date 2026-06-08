FROM node:22-bookworm-slim
RUN npm install -g @notionhq/notion-mcp-server@latest
EXPOSE 3000
CMD ["notion-mcp-server", "--transport", "http", "--port", "3000", "--disable-auth"]
