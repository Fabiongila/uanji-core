#!/usr/bin/env bash
# Gera a aplicação macOS (.app e .dmg) para Intel (x86_64).
# Requisitos: Rust (rustup), Xcode Command Line Tools, Node, ambiente Python do backend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

command -v cargo >/dev/null || { echo "Rust não encontrado. Instale com rustup (ver README)."; exit 1; }

echo "1/3 Testes"
(cd backend && .venv/bin/pytest -q)
(cd frontend && npx vitest run)

echo "2/3 Backend empacotado (PyInstaller, onedir)"
(cd backend && .venv/bin/pyinstaller packaging/uanji-backend.spec --noconfirm --distpath dist --workpath build)

echo "3/3 Aplicação Tauri"
frontend/node_modules/.bin/tauri build --target x86_64-apple-darwin
echo "Artefactos em src-tauri/target/x86_64-apple-darwin/release/bundle/"
