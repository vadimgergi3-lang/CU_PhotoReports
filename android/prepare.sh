#!/usr/bin/env bash
# Копирует модули генератора из корня проекта в android/ (если они есть).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

echo "[*] ROOT=$ROOT"
echo "[*] HERE=$HERE"

for f in config.py docgen.py continue_report.py; do
  if [ -f "$ROOT/$f" ]; then
    cp -f "$ROOT/$f" "$HERE/"
    echo "  copied $f"
  elif [ -f "$HERE/$f" ]; then
    echo "  $f already in android/"
  else
    echo "  WARNING: $f not found"
  fi
done

if [ -d "$ROOT/assets" ]; then
  rm -rf "$HERE/assets"
  cp -r "$ROOT/assets" "$HERE/assets"
  echo "  copied assets/"
elif [ -d "$HERE/assets" ]; then
  echo "  assets/ already present"
else
  echo "  WARNING: assets/ not found"
fi

echo "[OK] prepare done"
ls -la "$HERE"
