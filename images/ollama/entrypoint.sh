#!/bin/bash
ollama serve &
until ollama list >/dev/null 2>&1; do sleep 1; done
ollama pull "${OLLAMA_MODEL:-nomic-embed-text}"
wait
