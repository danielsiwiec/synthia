FROM node:22-bookworm-slim
RUN npm install -g @doist/todoist-mcp@latest
ENV PORT=8000
EXPOSE 8000
CMD ["todoist-mcp-http"]
