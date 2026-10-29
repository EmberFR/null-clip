# Maintainer: EmberFR <https://github.com/EmberFR/null-clip>
pkgname=null-clips-git
pkgver=1.0.0
pkgrel=1
pkgdesc="Open-source Linux GPU replay buffer & MP4 game clipper (gpu-screen-recorder + FFmpeg)"
arch=('x86_64')
url="https://github.com/EmberFR/null-clip"
license=('MIT')
depends=('gpu-screen-recorder' 'ffmpeg' 'wl-clipboard' 'curl' 'python' 'python-gobject' 'gtk3')
makedepends=('git')
provides=('null-clips')
conflicts=('null-clips')
source=("git+https://github.com/EmberFR/null-clip.git")
sha256sums=('SKIP')

package() {
  cd "$srcdir/null-clip"
  install -Dm755 null-clips.py "$pkgdir/usr/bin/null-clips"
  install -Dm644 LICENSE "$pkgdir/usr/share/licenses/$pkgname/LICENSE"

  install -dm755 "$pkgdir/usr/share/applications"
  cat << 'EOF' > "$pkgdir/usr/share/applications/null-clips.desktop"
[Desktop Entry]
Name=null-clips
Comment=Native Linux GPU Replay Buffer & H.264 MP4 Clipper
Exec=/usr/bin/null-clips
Icon=null-clips
Terminal=false
Type=Application
StartupWMClass=null-clips
Categories=AudioVideo;Video;Recorder;Game;
EOF
}
