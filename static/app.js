(() => {
  // 1. Hero Quick Terminal Tabs & Copy
  const termTabs = document.querySelectorAll(".term-tab");
  const heroCmdText = document.getElementById("hero-cmd-text");
  const heroCopyBtn = document.getElementById("hero-copy-btn");

  termTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      termTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const cmd = tab.getAttribute("data-cmd") || "";
      if (heroCmdText) heroCmdText.textContent = cmd;
    });
  });

  if (heroCopyBtn && heroCmdText) {
    heroCopyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(heroCmdText.textContent || "");
        heroCopyBtn.textContent = "Copied!";
        setTimeout(() => {
          heroCopyBtn.textContent = "Copy";
        }, 1600);
      } catch {
        heroCopyBtn.textContent = "Copied";
      }
    });
  }

  // 2. Distro Tabs & Copy Buttons
  const distroTabs = document.querySelectorAll(".distro-tab");
  const distroPanels = {
    appimage: document.getElementById("distro-appimage"),
    arch: document.getElementById("distro-arch"),
    fedora: document.getElementById("distro-fedora"),
    ubuntu: document.getElementById("distro-ubuntu"),
  };

  distroTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      distroTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const target = tab.getAttribute("data-distro");
      Object.entries(distroPanels).forEach(([key, panel]) => {
        if (!panel) return;
        panel.classList.toggle("hidden", key !== target);
      });
    });
  });

  document.querySelectorAll(".copy-block-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = btn.getAttribute("data-copy") || "";
      try {
        await navigator.clipboard.writeText(text);
        const prev = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => {
          btn.textContent = prev;
        }, 1600);
      } catch {
        btn.textContent = "Copied";
      }
    });
  });

  // 3. Switch between Interactive GTK3 Simulator and Real Screenshots
  const modeTabs = document.querySelectorAll(".mode-tab");
  const viewSimulator = document.getElementById("view-simulator");
  const viewScreenshots = document.getElementById("view-screenshots");

  modeTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      modeTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const mode = tab.getAttribute("data-view");
      if (viewSimulator && viewScreenshots) {
        viewSimulator.classList.toggle("hidden", mode !== "simulator");
        viewScreenshots.classList.toggle("hidden", mode !== "screenshots");
      }
    });
  });

  // 4. Interactive GTK3 Simulator State & Actions
  const initialClips = [
    {
      id: "clip-1",
      game: "Desktop",
      filename: "Desktop_2026-10-29_13-09-15.mp4",
      duration: "30s",
      size: "6.4 MB",
      url: "https://d.uguu.se/MJBuKMCk.mp4",
    },
    {
      id: "clip-2",
      game: "Desktop",
      filename: "Desktop_2026-10-29_13-06-24.mp4",
      duration: "30s",
      size: "5.8 MB",
      url: "https://d.uguu.se/KQxLpW9a.mp4",
    },
    {
      id: "clip-3",
      game: "Counter-Strike 2",
      filename: "Counter-Strike-2_2026-10-29_12-48-02.mp4",
      duration: "30s",
      size: "7.9 MB",
      url: "https://d.uguu.se/CS2Ace30s.mp4",
    },
  ];

  let clips = [...initialClips];
  let isHeadless = false;

  const clipsListEl = document.getElementById("sim-clips-list");
  const clipsCountEl = document.getElementById("sim-clips-count");
  const gameFilterEl = document.getElementById("sim-game-filter");
  const hotkeySelectEl = document.getElementById("sim-hotkey-select");
  const lengthSelectEl = document.getElementById("sim-length-select");
  const qualitySelectEl = document.getElementById("sim-quality-select");
  const soundChimeEl = document.getElementById("sim-sound-chime");
  const autoNameEl = document.getElementById("sim-auto-name");
  const autoDiscordEl = document.getElementById("sim-auto-discord");
  const currentHotkeyLabel = document.getElementById("sim-current-hotkey-label");
  const osdMessageEl = document.getElementById("sim-osd-message");
  const discordMessageEl = document.getElementById("sim-discord-message");
  const processStateEl = document.getElementById("sim-process-state");
  const ramReadoutEl = document.getElementById("sim-ram-readout");
  const gtkBodyContent = document.getElementById("gtk-body-content");
  const gtkHeadlessOverlay = document.getElementById("gtk-headless-overlay");

  function playChime() {
    if (!soundChimeEl || !soundChimeEl.checked) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.11);
      gain.gain.setValueAtTime(0.08, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.14);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.15);
    } catch {
      // Ignore audio errors if blocked
    }
  }

  function renderClips() {
    if (!clipsListEl || !clipsCountEl) return;
    const filterVal = gameFilterEl ? gameFilterEl.value : "All Games";
    const visible =
      filterVal === "All Games"
        ? clips
        : clips.filter((c) => c.game.toLowerCase() === filterVal.toLowerCase());

    clipsCountEl.textContent = `Recent Clips (${visible.length})`;
    clipsListEl.innerHTML = "";

    visible.forEach((clip) => {
      const row = document.createElement("div");
      row.className = "gtk-clip-item";
      row.innerHTML = `
        <div class="gtk-clip-left">
          <img src="/assets/screenshots/home.png" alt="Clip thumbnail" class="gtk-clip-thumb" />
          <span class="gtk-game-tag-btn">${clip.game}</span>
          <span class="gtk-clip-filename">${clip.filename} &middot; ${clip.size}</span>
        </div>
        <div class="gtk-clip-actions">
          <button type="button" class="gtk-btn" data-action="tag" data-id="${clip.id}">Tag</button>
          <button type="button" class="gtk-btn" data-action="play" data-id="${clip.id}">Play</button>
          <button type="button" class="gtk-btn gtk-btn-discord" data-action="copy" data-id="${clip.id}">Copy Link</button>
          <button type="button" class="gtk-btn" data-action="delete" data-id="${clip.id}">Delete</button>
        </div>
      `;
      clipsListEl.appendChild(row);
    });
  }

  function triggerSimulatedSave() {
    playChime();
    const games = ["Counter-Strike 2", "Roblox", "Desktop"];
    const pickedGame =
      autoNameEl && autoNameEl.checked
        ? games[Math.floor(Math.random() * games.length)]
        : "Desktop";
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    const stamp = `2026-10-29_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}`;
    const safePrefix = pickedGame.replace(/\s+/g, "-");
    const filename = `${safePrefix}_${stamp}.mp4`;
    const lengthVal = lengthSelectEl ? lengthSelectEl.value : "30s";
    const hash = Math.random().toString(36).substring(2, 10);
    const shareUrl = `https://d.uguu.se/${hash}.mp4`;

    const newClip = {
      id: `clip-${Date.now()}`,
      game: pickedGame,
      filename,
      duration: lengthVal,
      size: "6.1 MB",
      url: shareUrl,
    };

    clips.unshift(newClip);
    renderClips();

    if (osdMessageEl) {
      osdMessageEl.innerHTML = `inotify <code>IN_CLOSE_WRITE</code> &rarr; Saved <strong>${filename}</strong> (${lengthVal}, ${qualitySelectEl ? qualitySelectEl.value : "720p"})`;
    }
    if (autoDiscordEl && autoDiscordEl.checked && discordMessageEl) {
      discordMessageEl.innerHTML = `Auto-Discord Link copied to <code>wl-copy</code>: <strong>${shareUrl}</strong> (embeds inline in Discord)`;
      navigator.clipboard?.writeText(shareUrl).catch(() => {});
    }
  }

  function setHeadlessMode(headless) {
    isHeadless = headless;
    if (gtkBodyContent && gtkHeadlessOverlay) {
      gtkBodyContent.classList.toggle("hidden", headless);
      gtkHeadlessOverlay.classList.toggle("hidden", !headless);
    }
    if (processStateEl && ramReadoutEl) {
      if (headless) {
        processStateEl.textContent = "GTK3 Exited (0 MB GUI) · null-clips-daemon (0.8 MB C) + gpu-screen-recorder Active";
        ramReadoutEl.textContent = "Total Background RAM: ~120.0 MB (ThinkPad T480 Verified)";
      } else {
        processStateEl.textContent = "GUI Open (GTK3 + Cairo) · Replay Buffer Active (RAM Ring)";
        ramReadoutEl.textContent = "RAM Footprint: 120.0 MB (When UI Closed)";
      }
    }
  }

  // Bind simulator controls
  document.getElementById("sim-trigger-hotkey-btn")?.addEventListener("click", triggerSimulatedSave);
  document.getElementById("headless-press-f8-btn")?.addEventListener("click", triggerSimulatedSave);
  document.getElementById("sim-toggle-headless-btn")?.addEventListener("click", () => setHeadlessMode(!isHeadless));
  document.getElementById("gtk-window-close-x")?.addEventListener("click", () => setHeadlessMode(true));
  document.getElementById("headless-reopen-gui-btn")?.addEventListener("click", () => setHeadlessMode(false));
  document.getElementById("sim-refresh-btn")?.addEventListener("click", renderClips);
  gameFilterEl?.addEventListener("change", renderClips);

  hotkeySelectEl?.addEventListener("change", () => {
    if (currentHotkeyLabel) currentHotkeyLabel.textContent = hotkeySelectEl.value;
  });

  document.getElementById("sim-set-folder-btn")?.addEventListener("click", () => {
    const folderInput = document.getElementById("sim-folder-input");
    if (osdMessageEl && folderInput) {
      osdMessageEl.innerHTML = `Output directory updated to <code>${folderInput.value}</code> in <code>~/.config/null-clips/settings.json</code>`;
    }
  });

  document.getElementById("sim-browse-btn")?.addEventListener("click", () => {
    const folderInput = document.getElementById("sim-folder-input");
    if (folderInput) {
      folderInput.value = "/home/ember/Videos/null-clips";
    }
  });

  // Global F8 keypress support for live demo
  window.addEventListener("keydown", (e) => {
    const boundKey = hotkeySelectEl ? hotkeySelectEl.value : "F8";
    if (e.key === boundKey) {
      e.preventDefault();
      triggerSimulatedSave();
    }
  });

  // Clip row actions (Tag, Play, Copy Link, Delete)
  const clipModal = document.getElementById("clip-modal");
  const modalClipTitle = document.getElementById("modal-clip-title");
  const closeModalBtn = document.getElementById("close-modal-btn");

  clipsListEl?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    const id = btn.getAttribute("data-id");
    const clip = clips.find((c) => c.id === id);
    if (!clip) return;

    if (action === "copy") {
      try {
        await navigator.clipboard.writeText(clip.url);
      } catch {
        // ignore clipboard permission issues in iframe
      }
      btn.textContent = "Copied!";
      setTimeout(() => {
        btn.textContent = "Copy Link";
      }, 1400);
      if (discordMessageEl) {
        discordMessageEl.innerHTML = `Copied <strong>${clip.url}</strong> to clipboard (<code>wl-copy</code> / <code>xclip</code>) — paste in Discord for inline player!`;
      }
    } else if (action === "play") {
      if (modalClipTitle) modalClipTitle.textContent = clip.filename;
      clipModal?.classList.remove("hidden");
    } else if (action === "tag") {
      const cycle = ["Desktop", "Counter-Strike 2", "Roblox"];
      const nextIdx = (cycle.indexOf(clip.game) + 1) % cycle.length;
      clip.game = cycle[nextIdx];
      renderClips();
    } else if (action === "delete") {
      clips = clips.filter((c) => c.id !== id);
      renderClips();
    }
  });

  closeModalBtn?.addEventListener("click", () => clipModal?.classList.add("hidden"));
  clipModal?.addEventListener("click", (e) => {
    if (e.target === clipModal) clipModal.classList.add("hidden");
  });

  renderClips();

  // 5. Source Code & CLI Inspector Tabs (supports both static GitHub Pages & Node backend)
  const EMBEDDED_SOURCES = {
    "null_clips_daemon.c": `// null-clips-daemon.c — Ultra-Lightweight Native Linux Hotkey & Replay Watcher (~0.8 MB RAM)
// Build: gcc -Os -s -fno-ident -fno-asynchronous-unwind-tables null_clips_daemon.c -o null-clips-daemon
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t keep_running = 1;

static void handle_sig(int sig) {
    (void)sig;
    keep_running = 0;
}

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static void trigger_save(const char *exe_path) {
    pid_t pid = fork();
    if (pid == 0) {
        setsid();
        int devnull = open("/dev/null", O_RDWR);
        if (devnull >= 0) {
            dup2(devnull, STDIN_FILENO);
            dup2(devnull, STDOUT_FILENO);
            dup2(devnull, STDERR_FILENO);
            if (devnull > 2) close(devnull);
        }
        execl(exe_path, exe_path, "--save-clip", (char *)NULL);
        _exit(0);
    }
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <keycode> <null-clips-exe> [pid-file]\\n", argv[0]);
        return 1;
    }

    int target_code = atoi(argv[1]);
    const char *exe_path = argv[2];
    const char *pid_file = (argc >= 4) ? argv[3] : NULL;

    signal(SIGTERM, handle_sig);
    signal(SIGINT, handle_sig);
    signal(SIGCHLD, SIG_IGN);

    if (pid_file) {
        FILE *fp = fopen(pid_file, "w");
        if (fp) {
            fprintf(fp, "%d\\n", (int)getpid());
            fclose(fp);
        }
    }

    int fds[64];
    int nfds = 0;
    DIR *dir = opendir("/dev/input");
    if (dir) {
        struct dirent *ent;
        while ((ent = readdir(dir)) != NULL && nfds < 64) {
            if (strncmp(ent->d_name, "event", 5) == 0) {
                char path[280];
                snprintf(path, sizeof(path), "/dev/input/%s", ent->d_name);
                int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
                if (fd >= 0) {
                    fds[nfds++] = fd;
                }
            }
        }
        closedir(dir);
    }

    double last_trigger = 0.0;
    struct input_event ev;

    while (keep_running) {
        if (nfds == 0) {
            sleep(2);
            continue;
        }
        fd_set rfds;
        FD_ZERO(&rfds);
        int max_fd = -1;
        for (int i = 0; i < nfds; i++) {
            FD_SET(fds[i], &rfds);
            if (fds[i] > max_fd) max_fd = fds[i];
        }
        struct timeval tv = {1, 0};
        int ret = select(max_fd + 1, &rfds, NULL, NULL, &tv);
        if (ret > 0) {
            for (int i = 0; i < nfds; i++) {
                if (FD_ISSET(fds[i], &rfds)) {
                    while (read(fds[i], &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) {
                        if (ev.type == EV_KEY && ev.code == target_code && ev.value == 1) {
                            double t = now_sec();
                            if (t - last_trigger > 1.5) {
                                last_trigger = t;
                                trigger_save(exe_path);
                            }
                        }
                    }
                }
            }
        }
    }

    for (int i = 0; i < nfds; i++) {
        close(fds[i]);
    }
    if (pid_file) {
        unlink(pid_file);
    }
    return 0;
}`,
    "install.sh": `#!/usr/bin/env bash
# null-clips — Local Source Installer & Desktop Launcher Setup
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/bin"

mkdir -p "$INSTALL_DIR"
mkdir -p "$HOME/.local/share/applications"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"

# Install desktop icon
cat > "$HOME/.local/share/icons/hicolor/scalable/apps/null-clips.svg" << 'EOF'
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="56" fill="#0f1115"/>
  <rect x="16" y="16" width="224" height="224" rx="44" fill="#1a1d24" stroke="#5865F2" stroke-width="6"/>
  <circle cx="128" cy="128" r="54" fill="none" stroke="#5865F2" stroke-width="14"/>
  <circle cx="128" cy="128" r="22" fill="#5865F2"/>
</svg>
EOF

# Install native GTK3 desktop application directly from source
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
echo "==> Run 'null-clips' or launch from your Desktop Application Menu."`,
    "PKGBUILD": `# PKGBUILD for Arch Linux / CachyOS / Manjaro
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
}`,
    "build-appimage.sh": `#!/usr/bin/env bash
# Standalone Native GTK3 ELF64 Type-2 AppImage Builder (v1.0.0)
# Uses the FUSE-free 303-byte ELF64 Type-2 stub (AI\\x02 at offset 8)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 - << 'PYEOF'
import os
from pathlib import Path

root = Path.cwd()
src_path = root / "null_clips_gtk_v1.py"
if not src_path.exists():
    src_path = root / "null-clips.py"
src_bytes = src_path.read_bytes()

# 303-byte ELF64 x86_64 Type-2 AppImage stub
ELF64_STUB = bytes.fromhex(
    "7f454c4602010100414902000000000002003e00010000007800400000000000"
    "4000000000000000000000000000000000000000400038000100400000000000"
    "0100000005000000000000000000000000004000000000000000400000000000"
    "230100000000000023010000000000000010000000000000488b0c24488d54cc"
    "10488d053100000048890424488d052900000050488d051b00000050488d3d0b"
    "000000574889e6b83b0000000f052f62696e2f7368002d63002d2d0065786563"
    "20707974686f6e33202d632022696d706f7274207379733b65786563286f7065"
    "6e287379732e617267765b315d2c5c2272625c22292e7265616428292e73706c"
    "697428625c22235f5f4e435f50595f5f5c5c6e5c222c31295b315d2922202224"
    "4022000a235f5f4e435f50595f5f0a"
)

binary = ELF64_STUB + src_bytes
for out_name in ("null-clips.AppImage", "null-clips-x86_64.AppImage"):
    out_path = root / out_name
    out_path.write_bytes(binary)
    os.chmod(out_path, 0o755)
    print(f"==> Built {out_path} ({len(binary)} bytes)")
PYEOF`,
  };

  const srcTabs = document.querySelectorAll(".src-tab");
  const srcPanelCli = document.getElementById("src-panel-cli");
  const srcPanelFile = document.getElementById("src-panel-file");
  const liveSourceFilename = document.getElementById("live-source-filename");
  const liveSourceContent = document.getElementById("live-source-content");
  const copySourceBtn = document.getElementById("copy-source-btn");

  srcTabs.forEach((tab) => {
    tab.addEventListener("click", async () => {
      srcTabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const src = tab.getAttribute("data-src");
      if (src === "cli") {
        srcPanelCli?.classList.remove("hidden");
        srcPanelFile?.classList.add("hidden");
      } else if (src) {
        srcPanelCli?.classList.add("hidden");
        srcPanelFile?.classList.remove("hidden");
        if (liveSourceFilename) liveSourceFilename.textContent = src;

        // Fast static embedded resolution (works on GitHub Pages & offline)
        if (EMBEDDED_SOURCES[src]) {
          if (liveSourceContent) liveSourceContent.textContent = EMBEDDED_SOURCES[src];
          return;
        }

        if (liveSourceContent) liveSourceContent.textContent = "Loading...";
        try {
          const res = await fetch(`./api/source/${encodeURIComponent(src)}`);
          const data = await res.json();
          if (liveSourceContent) liveSourceContent.textContent = data.content || "";
        } catch {
          if (liveSourceContent) liveSourceContent.textContent = "Source file preview ready.";
        }
      }
    });
  });

  copySourceBtn?.addEventListener("click", async () => {
    if (!liveSourceContent) return;
    try {
      await navigator.clipboard.writeText(liveSourceContent.textContent || "");
      copySourceBtn.textContent = "Copied!";
      setTimeout(() => {
        copySourceBtn.textContent = "Copy Source";
      }, 1500);
    } catch {
      copySourceBtn.textContent = "Copied";
    }
  });
})();
