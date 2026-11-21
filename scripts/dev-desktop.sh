#!/usr/bin/env bash
# Janela desktop em modo de desenvolvimento (requer Rust). O Tauri lança o backend do venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
command -v cargo >/dev/null || { echo "Rust não encontrado. Instale com rustup (ver README)."; exit 1; }
frontend/node_modules/.bin/tauri dev
