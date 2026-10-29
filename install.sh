#!/usr/bin/env bash
# ==============================================================================
# null-clips — Local Source Installer & Desktop Launcher Setup
# Default: Builds & installs directly from the local repository source using
#          bun or npm (no prebuilt binary required).
# Optional: Pass --release to fetch the prebuilt AppImage from GitHub Releases.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"
REPO="EmberFR/null-clip"
RELEASE_URL="https://github.com/${REPO}/releases/latest/download/null-clips.AppImage"

mkdir -p "$INSTALL_DIR"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"

# Install icon
cat > "$HOME/.local/share/icons/hicolor/scalable/apps/null-clips.svg" << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="56" fill="#0f1115"/>
  <rect x="16" y="16" width="224" height="224" rx="44" fill="#1a1d24" stroke="#5865F2" stroke-width="6"/>
  <circle cx="128" cy="128" r="54" fill="none" stroke="#5865F2" stroke-width="14"/>
  <circle cx="128" cy="128" r="22" fill="#5865F2"/>
</svg>
EOF

# Optional flag: Download prebuilt AppImage from GitHub Releases
if [[ "${1:-}" == "--release" ]]; then
  TMP_APPIMAGE="/tmp/null-clips.AppImage"
  APPIMAGE_DEST="$INSTALL_DIR/null-clips.AppImage"
  echo "==> Downloading prebuilt null-clips.AppImage from GitHub Releases..."
  curl -fL "$RELEASE_URL" -o "$TMP_APPIMAGE"
  chmod +x "$TMP_APPIMAGE"

  if command -v shelly >/dev/null 2>&1; then
    echo "==> Registering AppImage with Shelly..."
    shelly install appimage "$TMP_APPIMAGE" && rm -f "$TMP_APPIMAGE" && exit 0
  fi

  mv -f "$TMP_APPIMAGE" "$APPIMAGE_DEST"
  chmod +x "$APPIMAGE_DEST"
  ln -sf "$APPIMAGE_DEST" "$INSTALL_DIR/null-clips"

  cat > "$HOME/.local/share/applications/null-clips.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=null-clips
GenericName=Linux GPU Replay Buffer
Comment=Lightweight Linux GPU Replay Buffer & MP4 Game Clipper
Exec=$APPIMAGE_DEST
Icon=null-clips
Terminal=false
Categories=AudioVideo;Recorder;
StartupWMClass=null-clips
X-AppImage-Version=1.0.0
EOF
  echo "==> Installed release AppImage to $APPIMAGE_DEST"
  exit 0
fi

# Default: Install native GTK3 desktop application directly from source
echo "==> Installing native GTK3 null-clips desktop app from $SCRIPT_DIR/null-clips.py..."
cp "$SCRIPT_DIR/null-clips.py" "$INSTALL_DIR/null-clips"
chmod +x "$INSTALL_DIR/null-clips"

cat > "$HOME/.local/share/applications/null-clips.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=null-clips
GenericName=Linux GPU Replay Buffer
Comment=Lightweight Native Linux GPU Replay Buffer & MP4 Game Clipper
Exec=$INSTALL_DIR/null-clips
Icon=null-clips
Terminal=false
Categories=AudioVideo;Video;Recorder;Utility;
StartupWMClass=null-clips
EOF

echo "==> Installed native GTK3 desktop app to $INSTALL_DIR/null-clips"
echo "==> Run 'null-clips' or launch from your Desktop Application Menu."
