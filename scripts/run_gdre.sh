#!/usr/bin/env bash
set -euo pipefail

ZIP_URL="https://github.com/GDRETools/gdsdecomp/releases/download/v2.4.0/GDRE_tools-v2.4.0-linux.zip"
DEST_DIR=".gdre_tools"
ZIP_NAME="GDRE_tools-v2.4.0-linux.zip"
ZIP_PATH="$DEST_DIR/$ZIP_NAME"

usage() {
  cat <<USAGE
Usage: $0 <path/to/file.pck> [output_dir]

Options:
  --docker      Force running GDRE inside ubuntu:22.04 Docker container
  --download-only  Only download/unpack GDRE and exit

Examples:
  $0 MonCurse_V0.6.9.3.5_LIN_PUBLIC.pck MonCurse_extracted
  FORCE_DOCKER=1 $0 game.pck outdir
  $0 --download-only
USAGE
}

if [ "$#" -lt 1 ]; then
  usage
  exit 1
fi

FORCE_DOCKER=0
DOWNLOAD_ONLY=0

if [ "$1" = "--download-only" ]; then
  DOWNLOAD_ONLY=1
  shift
fi

if [ "$#" -ge 1 ] && [ "$1" = "--docker" ]; then
  FORCE_DOCKER=1
  shift
fi

PCK_PATH="${1:-}"
OUT_DIR="${2:-}${PCK_PATH:+_extracted}"
if [ -z "$PCK_PATH" ] && [ $DOWNLOAD_ONLY -eq 0 ]; then
  usage
  exit 1
fi

mkdir -p "$DEST_DIR"

download_and_unpack() {
  if [ -f "$ZIP_PATH" ]; then
    echo "Using existing $ZIP_PATH"
  else
    echo "Downloading GDRE tools..."
    if command -v curl >/dev/null 2>&1; then
      curl -L --fail -o "$ZIP_PATH" "$ZIP_URL"
    else
      wget -O "$ZIP_PATH" "$ZIP_URL"
    fi
  fi

  echo "Unpacking to $DEST_DIR"
  if command -v unzip >/dev/null 2>&1; then
    unzip -o "$ZIP_PATH" -d "$DEST_DIR" >/dev/null
  else
    # try python fallback
    python3 - <<PY
import zipfile,sys
zf=zipfile.ZipFile('$ZIP_PATH')
zf.extractall('$DEST_DIR')
zf.close()
PY
  fi
}

find_binary() {
  BIN_REL=""
  # common name
  BIN_REL=$(find "$DEST_DIR" -type f -name 'gdre_tools.x86_64' -print -quit || true)
  if [ -z "$BIN_REL" ]; then
    BIN_REL=$(find "$DEST_DIR" -type f -name 'gdre_tools' -print -quit || true)
  fi
  echo "$BIN_REL"
}

download_and_unpack
BIN_REL=$(find_binary)
if [ -z "$BIN_REL" ]; then
  echo "ERROR: gdre binary not found under $DEST_DIR"
  exit 2
fi
chmod +x "$BIN_REL"
echo "Found binary: $BIN_REL"

if [ "$DOWNLOAD_ONLY" -eq 1 ]; then
  echo "Download/unpack complete. Binary at: $BIN_REL"
  exit 0
fi

PCK_ABS=$(realpath "$PCK_PATH")
OUT_DIR=${2:-"${PCK_PATH%.*}_extracted"}
mkdir -p "$OUT_DIR"

run_local() {
  echo "Running GDRE locally..."
  "$BIN_REL" --headless --extract="$PCK_ABS" --output="$OUT_DIR"
}

run_docker() {
  echo "Running GDRE inside ubuntu:22.04 Docker container..."
  # map current working tree into container at /workspaces/MC
  docker run --rm -v "$(pwd)":/workspaces/MC -w /workspaces/MC ubuntu:22.04 \
    bash -lc "chmod +x $BIN_REL || true; $BIN_REL --headless --extract=/workspaces/MC/$(basename \"$PCK_ABS\") --output=/workspaces/MC/$OUT_DIR"
}

# Try running locally unless forced to docker
if [ "$FORCE_DOCKER" -eq 1 ] || [ "${FORCE_DOCKER:-0}" = "1" ] || [ "${FORCE_DOCKER}" = "true" ]; then
  run_docker
  exit $?
fi

set +e
run_local
RC=$?
set -e
if [ $RC -ne 0 ]; then
  echo "Local run failed (exit $RC). Falling back to Docker run."
  run_docker
fi

echo "Done. Output directory: $OUT_DIR"
