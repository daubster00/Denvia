#!/usr/bin/bash
set -e
cd '/mnt/d/projects/Dental Chatbot/api'
source ~/.local/bin/env
export PYTHONPATH='/mnt/d/projects/Dental Chatbot:/mnt/d/projects/Dental Chatbot/vendor'
uv run --env-file ../.env alembic upgrade head
uv run --env-file ../.env uvicorn api.src.main:app --host 0.0.0.0 --port 8000 --reload
