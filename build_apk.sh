#!/usr/bin/env bash
# =============================================================================
#  build_apk.sh  –  Build the Tactical Mesh Android APK using Buildozer
#  Run this on Linux/macOS or inside WSL on Windows
# =============================================================================
#
#  PREREQUISITES (one-time setup):
#    sudo apt update && sudo apt install -y \
#        python3 python3-pip git zip unzip openjdk-17-jdk \
#        build-essential libssl-dev libffi-dev zlib1g-dev \
#        libltdl-dev cmake autoconf libtool pkg-config \
#        libncurses5-dev libncursesw5-dev libreadline-dev \
#        libgdbm-dev libdb-dev libexpat1-dev liblzma-dev \
#        libsqlite3-dev bzip2 libffi-dev
#
#    pip3 install buildozer cython==0.29.37
#
# =============================================================================

set -e

echo ""
echo "========================================="
echo " TACTICAL MESH – Android APK Build"
echo "========================================="
echo ""

# Go to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create data dir if missing
mkdir -p data/maps assets/fonts

# Clean previous build artifacts
echo "[1/4] Cleaning previous build..."
buildozer android clean 2>/dev/null || true

# Run the build
echo "[2/4] Building APK (this takes 15–30 min on first run)..."
buildozer -v android debug

echo "[3/4] Locating APK..."
APK_PATH=$(find bin/ -name "*.apk" | head -1)

if [ -z "$APK_PATH" ]; then
    echo "❌  APK not found – check buildozer errors above"
    exit 1
fi

echo ""
echo "========================================="
echo " ✅  BUILD COMPLETE"
echo " APK: $APK_PATH"
echo "========================================="
echo ""
echo "Install on Android via:"
echo "  adb install $APK_PATH"
echo "  -- OR --"
echo "  Copy $APK_PATH to your phone and open it"
echo ""
echo "FIRST RUN: Accept all permissions (Bluetooth, Location)"
echo "Then go to Settings → SCAN → tap your ESP32 → CONNECT"
echo ""
