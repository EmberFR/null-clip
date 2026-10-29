#!/usr/bin/env python3
# null-clips — Ultra-Lightweight Native Linux GPU Replay Buffer & 30s MP4 Clipper (v1.0.0)
# Debloated architecture:
# - Headless background daemon runs BEFORE importing GTK3 (~5 MB RAM, 0 MB GUI overhead when closed)
# - Strictly enforces 30-second replay clips (no disk-buffer multi-minute videos)
# - One-shot Game Tag detection on save + per-clip Game Tag editor & filter (zero background polling)
# - Reliable Auto-Discord Link & manual direct-MP4 upload with Wayland/X11 + GTK clipboard support
# - Single-track mixed Desktop + Mic audio so voice and game audio work in every player & Discord
import os
import re
import sys
import glob
import json
import math
import wave
import time
import uuid
import shutil
import struct
import select
import signal
import ctypes
import urllib.request
import subprocess
import threading
from pathlib import Path

APP_VERSION = "1.0.0"

DESKTOP_ENTRY_CONTENT = """[Desktop Entry]
Type=Application
Name=null-clips
GenericName=MP4 Game Clipper
Comment=Ultra-Lightweight Native Linux GPU Replay Buffer & 30s MP4 Clipper
Exec=null-clips
TryExec=null-clips
Icon=null-clips
Terminal=false
Categories=AudioVideo;Video;Recorder;Utility;
StartupWMClass=null-clips
X-AppImage-Name=null-clips
X-AppImage-Version=1.0.0
X-AppImage-Arch=x86_64
"""

ICON_SVG_CONTENT = """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="56" fill="#0f1115"/>
  <rect x="16" y="16" width="224" height="224" rx="44" fill="#1a1d24" stroke="#5865F2" stroke-width="6"/>
  <circle cx="128" cy="128" r="54" fill="none" stroke="#5865F2" stroke-width="14"/>
  <circle cx="128" cy="128" r="22" fill="#5865F2"/>
</svg>
"""

CONFIG_DIR = Path.home() / ".config" / "null-clips"
CONFIG_PATH = CONFIG_DIR / "settings.json"
LINKS_PATH = CONFIG_DIR / "shared_links.json"
TAGS_PATH = CONFIG_DIR / "clip_tags.json"
DEFAULT_FOLDER = Path.home() / "Videos" / "null-clips"
AUTOSTART_DESKTOP_PATH = Path.home() / ".config" / "autostart" / "null-clips.desktop"
PERSISTENT_BIN_PATH = Path.home() / ".local" / "bin" / "null-clips"
C_DAEMON_BIN_PATH = Path.home() / ".local" / "bin" / "null-clips-daemon"
DAEMON_PID_PATH = Path(f"/tmp/null-clips-daemon-{os.getuid()}.pid")
GSR_PID_PATH = Path(f"/tmp/null-clips-gsr-{os.getuid()}.pid")
SAVE_LOCK_PATH = Path(f"/tmp/null-clips-save-{os.getuid()}.lock")
CHIME_WAV_PATH = Path("/tmp/null-clips-chime.wav")

IN_CLOSE_WRITE = 0x00000008
IN_MOVED_TO = 0x00000080

C_DAEMON_SOURCE = r"""
#define _GNU_SOURCE
#include <dirent.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t keep_running = 1;
static void handle_sig(int sig) { (void)sig; keep_running = 0; }
static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}
static void trigger_save(const char *exe_path) {
    if (fork() == 0) {
        setsid();
        int dn = open("/dev/null", O_RDWR);
        if (dn >= 0) { dup2(dn, 0); dup2(dn, 1); dup2(dn, 2); if (dn > 2) close(dn); }
        execl(exe_path, exe_path, "--save-clip", (char *)NULL);
        _exit(0);
    }
}
int main(int argc, char **argv) {
    if (argc < 3) return 1;
    int target_code = atoi(argv[1]);
    const char *exe_path = argv[2];
    const char *pid_file = (argc >= 4) ? argv[3] : NULL;
    signal(SIGTERM, handle_sig);
    signal(SIGINT, handle_sig);
    signal(SIGCHLD, SIG_IGN);
    if (pid_file) {
        FILE *fp = fopen(pid_file, "w");
        if (fp) { fprintf(fp, "%d\n", (int)getpid()); fclose(fp); }
    }
    int fds[64], nfds = 0;
    DIR *dir = opendir("/dev/input");
    if (dir) {
        struct dirent *ent;
        while ((ent = readdir(dir)) != NULL && nfds < 64) {
            if (strncmp(ent->d_name, "event", 5) == 0) {
                char path[280];
                snprintf(path, sizeof(path), "/dev/input/%s", ent->d_name);
                int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
                if (fd >= 0) fds[nfds++] = fd;
            }
        }
        closedir(dir);
    }
    double last_trigger = 0.0;
    struct input_event ev;
    while (keep_running) {
        if (nfds == 0) { sleep(2); continue; }
        fd_set rfds; FD_ZERO(&rfds); int max_fd = -1;
        for (int i = 0; i < nfds; i++) { FD_SET(fds[i], &rfds); if (fds[i] > max_fd) max_fd = fds[i]; }
        struct timeval tv = {1, 0};
        if (select(max_fd + 1, &rfds, NULL, NULL, &tv) > 0) {
            for (int i = 0; i < nfds; i++) {
                if (FD_ISSET(fds[i], &rfds)) {
                    while (read(fds[i], &ev, sizeof(ev)) == (ssize_t)sizeof(ev)) {
                        if (ev.type == 1 && ev.code == target_code && ev.value == 1) {
                            double t = now_sec();
                            if (t - last_trigger > 1.5) { last_trigger = t; trigger_save(exe_path); }
                        }
                    }
                }
            }
        }
    }
    for (int i = 0; i < nfds; i++) close(fds[i]);
    if (pid_file) unlink(pid_file);
    return 0;
}
"""

EV_KEY = 0x01
KEYCODE_MAP = {
    "F8": 66,
    "F9": 67,
    "F10": 68,
    "F12": 88,
    "Insert": 110,
}

KNOWN_GAMES = (
    ("sober", "Roblox (Sober)"),
    ("roblox", "Roblox"),
    ("cs2", "Counter-Strike 2"),
    ("r5apex", "Apex Legends"),
    ("overwatch", "Overwatch 2"),
    ("minecraft", "Minecraft"),
    ("prismlauncher", "Minecraft"),
    ("lunarclient", "Minecraft"),
    ("dota2", "Dota 2"),
    ("hl2_linux", "Team Fortress 2"),
    ("tf_linux64", "Team Fortress 2"),
    ("eldenring", "Elden Ring"),
    ("rocketleague", "Rocket League"),
    ("gta5", "GTA V"),
    ("rustclient", "Rust"),
    ("terraria", "Terraria"),
    ("brawlhalla", "Brawlhalla"),
    ("warframe", "Warframe"),
    ("cyberpunk2077", "Cyberpunk 2077"),
    ("project8", "Deadlock"),
    ("marvel-win64", "Marvel Rivals"),
    ("marvelrivals", "Marvel Rivals"),
    ("discovery.exe", "THE FINALS"),
    ("valorant", "Valorant"),
    ("league of legends", "League of Legends"),
    ("genshinimpact", "Genshin Impact"),
    ("helldivers2", "Helldivers 2"),
    ("baldursgate3", "Baldur's Gate 3"),
    ("bg3", "Baldur's Gate 3"),
)

PRESET_GAME_TAGS = (
    "Roblox (Sober)",
    "Counter-Strike 2",
    "Apex Legends",
    "Minecraft",
    "Overwatch 2",
    "Marvel Rivals",
    "Deadlock",
    "THE FINALS",
    "Fortnite",
    "Valorant",
    "Team Fortress 2",
    "Dota 2",
    "GTA V",
    "Rust",
    "Elden Ring",
    "Rocket League",
    "Desktop",
)

IGNORED_WINDOW_KEYWORDS = (
    "null-clips",
    "gpu-screen-recorder",
    "discord",
    "vesktop",
    "firefox",
    "chrome",
    "chromium",
    "brave",
    "zen",
    "kitty",
    "alacritty",
    "konsole",
    "gnome-terminal",
    "foot",
    "wezterm",
    "dolphin",
    "nautilus",
    "thunar",
    "nemo",
    "code",
    "vscodium",
    "steam",
    "lutris",
    "heroic",
    "spotify",
    "obs",
)


def get_self_executable_path() -> str:
    env_appimage = os.environ.get("APPIMAGE", "").strip()
    if env_appimage and os.path.exists(env_appimage):
        return os.path.abspath(env_appimage)
    cand = sys.argv[1] if len(sys.argv) > 1 and sys.argv[0] == "-c" else sys.argv[0]
    if cand and os.path.exists(cand):
        return os.path.abspath(cand)
    if PERSISTENT_BIN_PATH.exists():
        return str(PERSISTENT_BIN_PATH)
    return os.path.abspath(sys.argv[0])


def get_user_cli_args() -> list:
    return sys.argv[2:] if len(sys.argv) > 1 and sys.argv[0] == "-c" else sys.argv[1:]


def load_settings() -> dict:
    defaults = {
        "outputDir": str(DEFAULT_FOLDER),
        "seconds": "30",
        "fps": "60",
        "resolution": "1280x720",
        "hotkey": "F8",
        "desktopAudio": True,
        "includeMic": True,
        "micDevice": "default_input",
        "soundEnabled": True,
        "osdNotifications": True,
        "autoShareDiscord": False,
        "autoRenameWithGame": True,
        "gameOnlyBuffer": False,
        "folderSizeCapGb": "0",
        "keepRunningClosed": True,
        "startOnBoot": AUTOSTART_DESKTOP_PATH.exists(),
    }
    try:
        if CONFIG_PATH.exists():
            saved = json.loads(CONFIG_PATH.read_text())
            if isinstance(saved, dict):
                defaults.update(saved)
    except Exception:
        pass
    if str(defaults.get("seconds")) not in ("15", "30", "60"):
        defaults["seconds"] = "30"
    if str(defaults.get("fps")) not in ("30", "60"):
        defaults["fps"] = "60"
    if str(defaults.get("resolution")) not in ("1280x720", "1920x1080"):
        defaults["resolution"] = "1280x720"
    if str(defaults.get("hotkey")) not in KEYCODE_MAP:
        defaults["hotkey"] = "F8"
    if str(defaults.get("folderSizeCapGb")) not in ("0", "5", "10", "25"):
        defaults["folderSizeCapGb"] = "0"
    return defaults


def save_settings(data: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def load_json_dict(path: Path) -> dict:
    try:
        if path.exists():
            d = json.loads(path.read_text())
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {}


def save_json_dict(path: Path, data: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def sanitize_game_filename_prefix(game_name: str) -> str:
    raw = (game_name or "Desktop").strip()
    if not raw or raw.lower() == "desktop":
        return "Desktop"
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", raw).strip("-")
    return (cleaned[:28] or "Game")


def rename_clip_with_game_prefix(file_path: Path, game_name: str) -> Path:
    """
    Rename saved clip on disk with its active Game Tag prefix:
    e.g. Replay_2026-10-28_18-30-05.mp4 -> Roblox-Sober_2026-10-28_18-30-05.mp4
    """
    if not file_path or not file_path.exists():
        return file_path
    prefix = sanitize_game_filename_prefix(game_name)
    stem = file_path.stem
    if stem.lower().startswith(prefix.lower() + "_"):
        return file_path
    # Strip generic gsr/replay/video prefixes before prepending the game tag
    clean_stem = re.sub(r"^(Replay|Clip|Video|gsr)[_-]+", "", stem, flags=re.IGNORECASE)
    new_name = f"{prefix}_{clean_stem}{file_path.suffix}"
    new_path = file_path.with_name(new_name)
    if new_path == file_path:
        return file_path
    try:
        if new_path.exists():
            new_path = file_path.with_name(f"{prefix}_{int(time.time())}_{clean_stem}{file_path.suffix}")
        file_path.rename(new_path)
        return new_path
    except Exception:
        return file_path


def get_clip_tag(tags: dict, file_path: Path) -> str:
    saved = tags.get(str(file_path)) or tags.get(file_path.name)
    if saved:
        return saved
    stem = file_path.stem
    if "_" in stem:
        first = stem.split("_", 1)[0].strip()
        if first and first.lower() not in ("replay", "clip", "video", "gsr") and not re.match(r"^\d{4}-\d{2}-\d{2}$", first):
            return first.replace("-", " ")
    return "Desktop"


def set_clip_tag(file_path: Path, game_name: str):
    tag = (game_name or "Desktop").strip()[:42] or "Desktop"
    tags = load_json_dict(TAGS_PATH)
    tags[str(file_path)] = tag
    tags[file_path.name] = tag
    save_json_dict(TAGS_PATH, tags)


def detect_active_game() -> str:
    """
    One-shot active game detector (runs ONLY when a clip is saved — zero idle CPU/RAM).
    Checks active compositor/X11 window first, then scans /proc for known games or Proton/Wine .exe.
    """
    # 1. Check Hyprland active window
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=0.8,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                info = json.loads(res.stdout)
                w_class = str(info.get("class") or "").strip()
                w_title = str(info.get("title") or "").strip()
                combined = f"{w_class} {w_title}".lower()
                for token, label in KNOWN_GAMES:
                    if token in combined:
                        return label
                if w_class and not any(k in combined for k in IGNORED_WINDOW_KEYWORDS):
                    if w_class.startswith("steam_app_"):
                        return (w_title or w_class)[:36]
                    return (w_title if len(w_title) <= 28 and w_title else w_class)[:36]
        except Exception:
            pass

    # 2. Check X11 active window title
    if shutil.which("xdotool"):
        try:
            res = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=0.6,
                check=False,
            )
            title = res.stdout.strip()
            if title:
                low = title.lower()
                for token, label in KNOWN_GAMES:
                    if token in low:
                        return label
                if not any(k in low for k in IGNORED_WINDOW_KEYWORDS):
                    return title[:36]
        except Exception:
            pass

    # 3. Fast one-shot scan of /proc for known game binaries or Proton/Wine .exe
    proton_candidate = ""
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                cmdline_raw = Path(f"/proc/{entry.name}/cmdline").read_bytes()
                if not cmdline_raw:
                    continue
                cmd_str = cmdline_raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
                cmd_low = cmd_str.lower()
                for token, label in KNOWN_GAMES:
                    if token in cmd_low:
                        return label
                if not proton_candidate and ".exe" in cmd_low and ("steamapps/common/" in cmd_low or "proton" in cmd_low):
                    m = re.search(r"steamapps/common/([^/\\]+)", cmd_str, re.IGNORECASE)
                    if m:
                        proton_candidate = m.group(1).strip()[:36]
            except Exception:
                continue
    except Exception:
        pass

    if proton_candidate:
        return proton_candidate
    return "Desktop"


def cleanup_disk_replay_junk(output_dir: Path):
    """Remove any leftover gsr-replay-*.gsr folders from older disk-storage runs."""
    try:
        if output_dir.exists():
            for item in output_dir.iterdir():
                if item.is_dir() and item.name.startswith("gsr-replay-"):
                    shutil.rmtree(item, ignore_errors=True)
    except Exception:
        pass


def get_clip_files(output_dir: Path) -> list:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        cleanup_disk_replay_junk(output_dir)
        return sorted(
            [
                p
                for p in output_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in (".mp4", ".mkv", ".webm")
                and not p.name.startswith(".")
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []


def enforce_folder_size_cap(output_dir: Path, cap_gb_val, keep_newest: Path = None) -> int:
    """
    One-shot folder size cap check (0 / 5 / 10 / 25 GB).
    Runs ONLY when a clip is saved — deletes oldest clips if total folder size exceeds cap.
    """
    try:
        cap_gb = int(str(cap_gb_val or "0"))
    except Exception:
        cap_gb = 0
    if cap_gb <= 0:
        return 0
    max_bytes = cap_gb * 1024 * 1024 * 1024
    files = get_clip_files(output_dir)
    if len(files) <= 1:
        return 0
    try:
        total_bytes = sum(f.stat().st_size for f in files if f.exists())
    except Exception:
        return 0
    if total_bytes <= max_bytes:
        return 0

    pruned = 0
    tags = load_json_dict(TAGS_PATH)
    links = load_json_dict(LINKS_PATH)
    changed_meta = False

    # files is sorted newest-first; iterate from oldest-first, never deleting keep_newest or index 0
    for old_file in reversed(files[1:]):
        if total_bytes <= max_bytes:
            break
        if keep_newest is not None and old_file == keep_newest:
            continue
        try:
            sz = old_file.stat().st_size
            old_file.unlink(missing_ok=True)
            total_bytes -= sz
            pruned += 1
            for k in (str(old_file), old_file.name):
                if k in tags:
                    tags.pop(k, None)
                    changed_meta = True
                if k in links:
                    links.pop(k, None)
                    changed_meta = True
        except Exception:
            pass

    if changed_meta:
        save_json_dict(TAGS_PATH, tags)
        save_json_dict(LINKS_PATH, links)
    return pruned


def probe_duration_seconds(file_path: Path) -> float:
    if shutil.which("ffprobe"):
        try:
            res = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(file_path),
                ],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            val = float(res.stdout.strip())
            if val > 0:
                return val
        except Exception:
            pass
    return 0.0


def wait_for_clip_ready(file_path: Path):
    """Wait until gpu-screen-recorder finishes flushing the MP4 file and its size stabilizes."""
    if not file_path:
        return
    prev_size = -1
    stable_ticks = 0
    for _ in range(25):
        try:
            if not file_path.exists():
                time.sleep(0.15)
                continue
            cur_size = file_path.stat().st_size
            if cur_size > 512 and cur_size == prev_size:
                stable_ticks += 1
                if stable_ticks >= 2:
                    break
            else:
                stable_ticks = 0
            prev_size = cur_size
        except Exception:
            pass
        time.sleep(0.15)


def enforce_exact_clip_duration(file_path: Path, target_seconds: int):
    """Ensure saved replay clip is never longer than target_seconds (lossless stream copy)."""
    if not file_path or not file_path.exists():
        return
    wait_for_clip_ready(file_path)
    if not shutil.which("ffmpeg"):
        return
    try:
        dur = probe_duration_seconds(file_path)
        if dur > float(target_seconds) + 2.5:
            tmp_out = file_path.with_name(f".trim_{file_path.name}")
            res = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-sseof",
                    f"-{int(target_seconds)}",
                    "-i",
                    str(file_path),
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(tmp_out),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15.0,
                check=False,
            )
            if res.returncode == 0 and tmp_out.exists() and tmp_out.stat().st_size > 1024:
                shutil.move(str(tmp_out), str(file_path))
            elif tmp_out.exists():
                tmp_out.unlink(missing_ok=True)
    except Exception:
        pass


def ensure_chime_wav():
    if CHIME_WAV_PATH.exists():
        return
    try:
        sr = 22050
        n = int(sr * 0.28)
        with wave.open(str(CHIME_WAV_PATH), "w") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            buf = bytearray()
            for i in range(n):
                t = i / sr
                freq = 587.33 if t < 0.12 else 880.0
                lt = t if t < 0.12 else (t - 0.12)
                env = math.exp(-lt * 14.0)
                val = int(math.sin(2.0 * math.pi * freq * t) * env * 12000)
                buf.extend(struct.pack("<h", max(-32767, min(32767, val))))
            w.writeframes(bytes(buf))
    except Exception:
        pass


def play_clip_chime():
    ensure_chime_wav()
    if not CHIME_WAV_PATH.exists():
        return
    wav_str = str(CHIME_WAV_PATH)
    for player in (["pw-play", wav_str], ["paplay", wav_str], ["aplay", "-q", wav_str]):
        if shutil.which(player[0]):
            subprocess.Popen(player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


def send_desktop_notification(title: str, body: str, enabled: bool = True):
    if not enabled:
        return
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(
                ["notify-send", "-a", "null-clips", "-t", "2500", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def list_microphone_devices():
    devices = [("default_input", "Default System Mic")]
    seen = {"default_input", "default_output"}
    if shutil.which("gpu-screen-recorder"):
        try:
            res = subprocess.run(
                ["gpu-screen-recorder", "--list-audio-devices"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            for raw_line in res.stdout.splitlines():
                if "|" not in raw_line:
                    continue
                dev_id, desc = [x.strip() for x in raw_line.split("|", 1)]
                if not dev_id or dev_id in seen or dev_id.endswith(".monitor") or "monitor of " in desc.lower():
                    continue
                seen.add(dev_id)
                label = (desc or dev_id)[:40]
                devices.append((dev_id, label))
        except Exception:
            pass
    return devices


def prepare_mic_device(selected_id: str) -> str:
    mic_dev = (selected_id or "default_input").strip()
    if shutil.which("pactl"):
        try:
            if mic_dev == "default_input":
                res = subprocess.run(
                    ["pactl", "get-default-source"],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    check=False,
                )
                def_src = res.stdout.strip()
                if not def_src or def_src.endswith(".monitor"):
                    for cand_id, _ in list_microphone_devices():
                        if cand_id != "default_input" and not cand_id.endswith(".monitor"):
                            mic_dev = cand_id
                            break
                else:
                    subprocess.run(
                        ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
            else:
                subprocess.run(
                    ["pactl", "set-source-mute", mic_dev, "0"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass
    return mic_dev or "default_input"


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    return Path(f"/proc/{pid}").exists()


def get_running_gsr_pid() -> int:
    try:
        if GSR_PID_PATH.exists():
            pid = int(GSR_PID_PATH.read_text().strip())
            if is_pid_alive(pid):
                comm = Path(f"/proc/{pid}/comm").read_text().strip()
                if "gpu-screen" in comm or "gsr" in comm:
                    return pid
    except Exception:
        pass
    try:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            comm = Path(f"/proc/{entry.name}/comm").read_text().strip()
            if "gpu-screen-rec" in comm:
                return int(entry.name)
    except Exception:
        pass
    return 0


def stop_all_gsr_processes():
    """Stop any running gpu-screen-recorder processes so duplicates never accumulate in RAM."""
    pid = get_running_gsr_pid()
    if pid > 0:
        try:
            os.kill(pid, signal.SIGINT)
        except Exception:
            pass
    subprocess.run(
        ["killall", "-SIGINT", "gpu-screen-recorder"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(10):
        if get_running_gsr_pid() == 0:
            break
        time.sleep(0.1)
    if get_running_gsr_pid() != 0:
        subprocess.run(
            ["killall", "-9", "gpu-screen-recorder"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    try:
        GSR_PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def stop_background_daemon():
    try:
        if DAEMON_PID_PATH.exists():
            pid = int(DAEMON_PID_PATH.read_text().strip())
            if is_pid_alive(pid) and pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
            DAEMON_PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def start_gsr_replay_buffer(cfg: dict, prefer_direct_screen: bool = False) -> int:
    """Start gpu-screen-recorder in low-RAM replay buffer mode and return its PID."""
    stop_all_gsr_processes()
    out_dir = Path(cfg.get("outputDir", str(DEFAULT_FOLDER))).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    cleanup_disk_replay_junk(out_dir)

    sec = str(cfg.get("seconds", "30"))
    fps = str(cfg.get("fps", "60"))
    res = str(cfg.get("resolution", "1280x720"))
    kbps = "2500" if res == "1280x720" else "4000"
    target_win = "screen" if prefer_direct_screen else "portal"

    inc_desktop = bool(cfg.get("desktopAudio", True))
    inc_mic = bool(cfg.get("includeMic", True))
    mic_dev = prepare_mic_device(str(cfg.get("micDevice", "default_input"))) if inc_mic else "default_input"

    audio_args = []
    if inc_desktop and inc_mic:
        audio_args = ["-a", f"default_output|{mic_dev}"]
    elif inc_desktop:
        audio_args = ["-a", "default_output"]
    elif inc_mic:
        audio_args = ["-a", mic_dev]

    env = os.environ.copy()
    env["MALLOC_ARENA_MAX"] = "2"

    cmd = [
        "gpu-screen-recorder",
        "-w",
        target_win,
        "-s",
        res,
        "-f",
        fps,
        "-r",
        sec,
        "-k",
        "h264",
        "-c",
        "mp4",
        "-replay-storage",
        "ram",
        "-bm",
        "cbr",
        "-q",
        kbps,
        "-v",
        "no",
    ] + audio_args + ["-o", str(out_dir)]

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(0.6)

    if proc.poll() is not None:
        fallback_win = "portal"
        cmd_fb = [
            "gpu-screen-recorder",
            "-w",
            fallback_win,
            "-s",
            res,
            "-f",
            fps,
            "-r",
            sec,
            "-k",
            "h264",
            "-c",
            "mp4",
            "-q",
            "medium",
        ] + audio_args + ["-o", str(out_dir)]
        proc = subprocess.Popen(
            cmd_fb,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    try:
        GSR_PID_PATH.write_text(str(proc.pid))
    except Exception:
        pass
    return proc.pid


def send_save_signal_to_gsr(target_seconds: int, use_rt_signal: bool = True) -> bool:
    """Trigger replay save on running gpu-screen-recorder using exact-timestamp signal when supported."""
    pid = get_running_gsr_pid()
    if pid <= 0:
        return False
    sig = signal.SIGUSR1
    if use_rt_signal and hasattr(signal, "SIGRTMIN"):
        if int(target_seconds) == 30:
            sig = signal.SIGRTMIN + 2
        elif int(target_seconds) == 60:
            sig = signal.SIGRTMIN + 3
    try:
        os.kill(pid, sig)
        return True
    except Exception:
        res = subprocess.run(["killall", "-SIGUSR1", "gpu-screen-recorder"], check=False)
        return res.returncode == 0


def _extract_upload_url(raw_out: str) -> str:
    text = (raw_out or "").strip()
    if not text:
        return ""
    if text.startswith("https://") and " " not in text and "\n" not in text:
        return text
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            files = data.get("files")
            if isinstance(files, list) and files and isinstance(files[0], dict):
                u = str(files[0].get("url") or "").replace("\\/", "/").strip()
                if u.startswith("https://"):
                    return u
            u = str(data.get("url") or "").replace("\\/", "/").strip()
            if u.startswith("https://"):
                return u
    except Exception:
        pass
    m = re.search(r"https://[^\s\"'<>\\]+", text.replace("\\/", "/"))
    return m.group(0) if m else ""


def _urllib_multipart_upload(url: str, field_name: str, file_path: Path) -> str:
    boundary = f"----NullClipsBoundary{uuid.uuid4().hex}"
    filename = file_path.name
    file_bytes = file_path.read_bytes()
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = header + file_bytes + footer
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) null-clips/1.0",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return _extract_upload_url(resp.read().decode("utf-8", errors="ignore"))


def upload_mp4_for_discord(file_path: Path) -> str:
    """
    Upload clip to a direct-MP4 host that embeds inline in Discord (Content-Type: video/mp4).
    Tries fast curl endpoints first (uguu.se, pomf2.lain.la, catbox.moe, qu.ax) then urllib fallback.
    """
    if not file_path or not file_path.exists():
        raise RuntimeError("Clip file not found")
    wait_for_clip_ready(file_path)
    path_str = str(file_path)

    if shutil.which("curl"):
        for cmd in (
            [
                "curl",
                "-sS",
                "--max-time",
                "75",
                "-A",
                "Mozilla/5.0",
                "-F",
                f"files[]=@{path_str};type=video/mp4",
                "https://uguu.se/upload?output=text",
            ],
            [
                "curl",
                "-sS",
                "--max-time",
                "75",
                "-A",
                "Mozilla/5.0",
                "-F",
                f"files[]=@{path_str};type=video/mp4",
                "https://pomf2.lain.la/upload.php",
            ],
            [
                "curl",
                "-sS",
                "--max-time",
                "75",
                "-A",
                "Mozilla/5.0",
                "-F",
                "reqtype=fileupload",
                "-F",
                f"fileToUpload=@{path_str};type=video/mp4",
                "https://catbox.moe/user/api.php",
            ],
            [
                "curl",
                "-sS",
                "--max-time",
                "75",
                "-A",
                "Mozilla/5.0",
                "-F",
                f"files[]=@{path_str};type=video/mp4",
                "https://qu.ax/upload.php",
            ],
        ):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=80, check=False)
                url = _extract_upload_url(res.stdout)
                if url.startswith("https://"):
                    return url
            except Exception:
                pass

    for endpoint in ("https://uguu.se/upload?output=text", "https://pomf2.lain.la/upload.php"):
        try:
            url = _urllib_multipart_upload(endpoint, "files[]", file_path)
            if url.startswith("https://"):
                return url
        except Exception:
            pass

    raise RuntimeError("Upload failed (check internet connection)")


def copy_text_system_clipboard(text: str):
    """
    Copy text to Wayland and X11 clipboards without blocking or killing wl-copy's background holder.
    """
    if not text:
        return
    if shutil.which("wl-copy"):
        try:
            subprocess.Popen(
                ["wl-copy", "--", text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception:
            pass
    if shutil.which("xclip"):
        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            p.communicate(input=text.encode("utf-8"), timeout=1.5)
        except Exception:
            pass
    elif shutil.which("xsel"):
        try:
            p = subprocess.Popen(
                ["xsel", "--clipboard", "--input"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            p.communicate(input=text.encode("utf-8"), timeout=1.5)
        except Exception:
            pass


def register_compositor_shortcut(hotkey: str):
    exe = get_self_executable_path()
    save_cmd = f"{exe} --save-clip"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        subprocess.run(
            ["hyprctl", "keyword", "bind", f", {hotkey}, exec, {save_cmd}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        subprocess.run(
            ["swaymsg", "bindsym", hotkey, "exec", save_cmd],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def wait_for_new_clip_inotify(out_dir: Path, before_names: set, target_sec: int, timeout_sec: float = 4.4):
    """
    Wait for gpu-screen-recorder to finish writing the MP4 using Linux kernel inotify
    (IN_CLOSE_WRITE | IN_MOVED_TO). Wakes up the exact millisecond the clip file is closed,
    with zero 200ms sleep polling overhead. Falls back cleanly if inotify is unavailable.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    inotify_fd = -1
    watch_wd = -1
    libc = None

    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        inotify_fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if inotify_fd >= 0:
            watch_wd = libc.inotify_add_watch(
                inotify_fd,
                str(out_dir).encode("utf-8"),
                IN_CLOSE_WRITE | IN_MOVED_TO,
            )
    except Exception:
        inotify_fd = -1

    try:
        deadline = time.monotonic() + timeout_sec
        sent_fallback_sig = False

        while time.monotonic() < deadline:
            # Check if file is already present and non-empty
            for f in get_clip_files(out_dir):
                if f.name not in before_names:
                    try:
                        if f.stat().st_size > 1024:
                            return f
                    except Exception:
                        pass

            elapsed = timeout_sec - (deadline - time.monotonic())
            if not sent_fallback_sig and elapsed >= 0.85 and int(target_sec) in (30, 60):
                sent_fallback_sig = True
                send_save_signal_to_gsr(target_sec, use_rt_signal=False)

            remaining = max(0.05, min(0.35, deadline - time.monotonic()))
            if inotify_fd >= 0:
                rlist, _, _ = select.select([inotify_fd], [], [], remaining)
                if rlist:
                    try:
                        os.read(inotify_fd, 4096)
                    except Exception:
                        pass
            else:
                time.sleep(0.12)
    finally:
        if inotify_fd >= 0:
            try:
                if libc is not None and watch_wd >= 0:
                    libc.inotify_rm_watch(inotify_fd, watch_wd)
            except Exception:
                pass
            try:
                os.close(inotify_fd)
            except Exception:
                pass

    return None


def save_replay_clip_file(cfg: dict):
    """
    Trigger gpu-screen-recorder save, detect completion via Linux kernel inotify,
    auto-rename with active Game Tag, and enforce exact clip duration.
    Uses a lock timestamp so simultaneous compositor + evdev triggers never double-save.
    """
    now = time.time()
    try:
        if SAVE_LOCK_PATH.exists() and (now - SAVE_LOCK_PATH.stat().st_mtime) < 1.5:
            return None
        SAVE_LOCK_PATH.write_text(str(now))
    except Exception:
        pass

    out_dir = Path(cfg.get("outputDir", str(DEFAULT_FOLDER))).expanduser()
    target_sec = int(cfg.get("seconds", "30"))
    detected_game = detect_active_game()
    before = set(p.name for p in get_clip_files(out_dir))

    if not send_save_signal_to_gsr(target_sec, use_rt_signal=True):
        return None

    if cfg.get("soundEnabled", True):
        play_clip_chime()

    newest = wait_for_new_clip_inotify(out_dir, before, target_sec, timeout_sec=4.4)

    if newest is None:
        files = get_clip_files(out_dir)
        if files and (time.time() - files[0].stat().st_mtime) < 6.0:
            newest = files[0]

    if newest is not None:
        enforce_exact_clip_duration(newest, target_sec)
        if cfg.get("autoRenameWithGame", True):
            newest = rename_clip_with_game_prefix(newest, detected_game)
        set_clip_tag(newest, detected_game)
        pruned = enforce_folder_size_cap(out_dir, cfg.get("folderSizeCapGb", "0"), keep_newest=newest)
        osd_on = bool(cfg.get("osdNotifications", True))
        prune_note = f" · Pruned {pruned} old clip(s)" if pruned > 0 else ""
        send_desktop_notification(
            f"null-clips · Saved {target_sec}s Clip",
            f"[{detected_game}] {newest.name}{prune_note}",
            enabled=osd_on,
        )

    return newest


def trigger_save_and_postprocess(cfg: dict):
    """Full headless save + Game Tag + Auto-Discord upload & clipboard copy."""
    newest = save_replay_clip_file(cfg)
    osd_on = bool(cfg.get("osdNotifications", True))
    if newest is not None and cfg.get("autoShareDiscord", False):
        try:
            url = upload_mp4_for_discord(newest)
            links = load_json_dict(LINKS_PATH)
            links[str(newest)] = url
            links[newest.name] = url
            save_json_dict(LINKS_PATH, links)
            copy_text_system_clipboard(url)
            send_desktop_notification("null-clips · Discord Link Copied", url, enabled=osd_on)
        except Exception as e:
            send_desktop_notification("null-clips · Auto-Discord Upload Failed", str(e), enabled=osd_on)
    return newest


def ensure_c_daemon_binary() -> str:
    """
    Compile or locate the ultra-lightweight native C daemon (~0.8 MB RSS) if gcc/cc is installed.
    Returns the path to the executable or empty string if unavailable.
    """
    try:
        if C_DAEMON_BIN_PATH.exists() and os.access(str(C_DAEMON_BIN_PATH), os.X_OK):
            return str(C_DAEMON_BIN_PATH)
        compiler = shutil.which("gcc") or shutil.which("cc") or shutil.which("clang")
        if not compiler:
            return ""
        C_DAEMON_BIN_PATH.parent.mkdir(parents=True, exist_ok=True)
        src_tmp = Path(f"/tmp/null-clips-daemon-{os.getuid()}.c")
        src_tmp.write_text(C_DAEMON_SOURCE)
        res = subprocess.run(
            [
                compiler,
                "-Os",
                "-s",
                "-fno-ident",
                "-fno-asynchronous-unwind-tables",
                str(src_tmp),
                "-o",
                str(C_DAEMON_BIN_PATH),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8.0,
            check=False,
        )
        src_tmp.unlink(missing_ok=True)
        if res.returncode == 0 and C_DAEMON_BIN_PATH.exists():
            os.chmod(str(C_DAEMON_BIN_PATH), 0o755)
            return str(C_DAEMON_BIN_PATH)
    except Exception:
        pass
    return ""


def spawn_background_watcher(cfg: dict):
    """
    When closing the GTK3 window, launch the ~0.8 MB native C daemon if Game-Only auto-pause
    is not needed, or the headless Python watcher if Game-Only auto-pause is active.
    """
    exe = get_self_executable_path()
    if not cfg.get("gameOnlyBuffer", False):
        c_bin = ensure_c_daemon_binary()
        if c_bin:
            keycode = KEYCODE_MAP.get(cfg.get("hotkey", "F8"), 66)
            subprocess.Popen(
                [c_bin, str(keycode), exe, str(DAEMON_PID_PATH)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return
    subprocess.Popen(
        [exe, "--daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def run_headless_background_daemon(auto_start_gsr: bool = False):
    """
    Ultra-low-RAM headless hotkey & Game-Only auto-pause watcher.
    Runs WITHOUT importing GTK3/Cairo/Pango so background RAM usage stays minimal when window is closed.
    """
    stop_background_daemon()
    try:
        DAEMON_PID_PATH.write_text(str(os.getpid()))
    except Exception:
        pass

    cfg = load_settings()
    game_only = bool(cfg.get("gameOnlyBuffer", False))
    register_compositor_shortcut(cfg.get("hotkey", "F8"))

    if auto_start_gsr and not game_only and get_running_gsr_pid() == 0 and shutil.which("gpu-screen-recorder"):
        start_gsr_replay_buffer(cfg, prefer_direct_screen=True)

    # If C daemon is available and game_only is off, exec directly into the ~0.8 MB native C binary!
    if not game_only:
        c_bin = ensure_c_daemon_binary()
        if c_bin:
            keycode = KEYCODE_MAP.get(cfg.get("hotkey", "F8"), 66)
            exe = get_self_executable_path()
            try:
                os.execv(c_bin, [c_bin, str(keycode), exe, str(DAEMON_PID_PATH)])
            except Exception:
                pass

    running = True

    def _sig_stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _sig_stop)
    signal.signal(signal.SIGINT, _sig_stop)

    event_struct = struct.Struct("llHHi")
    files = []
    for path in glob.glob("/dev/input/event*"):
        if os.access(path, os.R_OK):
            try:
                files.append(open(path, "rb", buffering=0))
            except Exception:
                pass

    last_trigger = 0.0
    last_game_check = 0.0
    target_code = KEYCODE_MAP.get(cfg.get("hotkey", "F8"), 66)

    while running:
        now = time.time()
        if game_only and (now - last_game_check) >= 4.0:
            last_game_check = now
            cfg = load_settings()
            game_only = bool(cfg.get("gameOnlyBuffer", False))
            if game_only and shutil.which("gpu-screen-recorder"):
                active_game = detect_active_game()
                gsr_alive = get_running_gsr_pid() > 0
                if active_game != "Desktop" and not gsr_alive:
                    start_gsr_replay_buffer(cfg, prefer_direct_screen=True)
                elif active_game == "Desktop" and gsr_alive:
                    stop_all_gsr_processes()

        if not game_only and get_running_gsr_pid() == 0 and not auto_start_gsr:
            break

        if files:
            try:
                rlist, _, _ = select.select(files, [], [], 1.0)
                for f in rlist:
                    data = f.read(event_struct.size)
                    if data and len(data) == event_struct.size:
                        _sec, _usec, ev_type, ev_code, ev_val = event_struct.unpack(data)
                        if ev_type == EV_KEY and ev_code == target_code and ev_val == 1:
                            t_now = time.time()
                            if t_now - last_trigger > 1.5:
                                last_trigger = t_now
                                cfg = load_settings()
                                threading.Thread(
                                    target=trigger_save_and_postprocess,
                                    args=(cfg,),
                                    daemon=True,
                                ).start()
            except Exception:
                time.sleep(1.0)
        else:
            time.sleep(2.0)

    for f in files:
        try:
            f.close()
        except Exception:
            pass
    try:
        DAEMON_PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    sys.exit(0)


def configure_autostart(enabled: bool) -> str:
    try:
        if not enabled:
            AUTOSTART_DESKTOP_PATH.unlink(missing_ok=True)
            return "Disabled Start on Boot."

        exe_src = get_self_executable_path()
        target_exec = exe_src
        try:
            PERSISTENT_BIN_PATH.parent.mkdir(parents=True, exist_ok=True)
            if os.path.exists(exe_src) and os.path.abspath(exe_src) != str(PERSISTENT_BIN_PATH):
                shutil.copyfile(exe_src, str(PERSISTENT_BIN_PATH))
                os.chmod(str(PERSISTENT_BIN_PATH), 0o755)
            if PERSISTENT_BIN_PATH.exists():
                target_exec = str(PERSISTENT_BIN_PATH)
        except Exception:
            pass

        AUTOSTART_DESKTOP_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_DESKTOP_PATH.write_text(
            f"""[Desktop Entry]
Type=Application
Name=null-clips
Comment=Start null-clips 30s Replay Buffer in Background on Boot
Exec={target_exec} --background
TryExec={target_exec}
Icon=null-clips
Terminal=false
Categories=AudioVideo;Video;Recorder;Utility;
X-GNOME-Autostart-enabled=true
StartupNotify=false
"""
        )
        return "Enabled Start on Boot (0 MB GUI overhead)."
    except Exception as e:
        return f"Start on Boot error: {e}"


def handle_cli_flags():
    user_args = get_user_cli_args()
    if not user_args:
        return

    exe_path = get_self_executable_path()
    flag = user_args[0]

    if flag == "--appimage-extract":
        root = Path.cwd() / "squashfs-root"
        (root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
        (root / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
        (root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps").mkdir(parents=True, exist_ok=True)

        (root / "null-clips.desktop").write_text(DESKTOP_ENTRY_CONTENT)
        (root / "usr" / "share" / "applications" / "null-clips.desktop").write_text(DESKTOP_ENTRY_CONTENT)
        (root / "null-clips.svg").write_text(ICON_SVG_CONTENT)
        (root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "null-clips.svg").write_text(
            ICON_SVG_CONTENT
        )
        (root / ".DirIcon").write_text(ICON_SVG_CONTENT)

        apprun = root / "AppRun"
        bin_target = root / "usr" / "bin" / "null-clips"
        try:
            shutil.copyfile(exe_path, apprun)
            shutil.copyfile(exe_path, bin_target)
            os.chmod(apprun, 0o755)
            os.chmod(bin_target, 0o755)
        except Exception:
            apprun.write_text('#!/bin/sh\nexec python3 "$0" "$@"\n')
            os.chmod(apprun, 0o755)
        sys.exit(0)

    if flag == "--appimage-updateinfo":
        print("")
        sys.exit(0)

    if flag in ("--appimage-version", "--version", "-v"):
        print(f"null-clips v{APP_VERSION}")
        sys.exit(0)

    if flag == "--appimage-offset":
        print("303")
        sys.exit(0)

    if flag in ("--appimage-help", "--help", "-h"):
        print(
            f"null-clips v{APP_VERSION}\n"
            "  --background   Run headless 30s replay daemon (no GTK3 RAM overhead)\n"
            "  --save-clip    Save last 30s clip immediately\n"
            "  --quit         Stop background daemon and replay buffer"
        )
        sys.exit(0)

    if flag == "--save-clip":
        trigger_save_and_postprocess(load_settings())
        sys.exit(0)

    if flag == "--quit":
        stop_background_daemon()
        stop_all_gsr_processes()
        sys.exit(0)

    if flag == "--daemon":
        run_headless_background_daemon(auto_start_gsr=False)

    if flag in ("--background", "--minimized", "--tray"):
        run_headless_background_daemon(auto_start_gsr=True)


# Process CLI & headless flags BEFORE importing GTK3 so background mode uses ~5 MB RAM
handle_cli_flags()
stop_background_daemon()

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
except Exception as e:
    print("Error loading GTK3 (python-gobject):", e, file=sys.stderr)
    sys.exit(1)

THUMB_CACHE_DIR = Path("/tmp/null-clips-thumbs")


def get_thumb_cache_path(video_path: Path) -> Path:
    try:
        st = video_path.stat()
        key = f"{video_path.stem}_{int(st.st_mtime)}_{st.st_size}.jpg"
    except Exception:
        key = f"{video_path.stem}.jpg"
    return THUMB_CACHE_DIR / key



def detect_distro_install_cmd() -> str:
    if shutil.which("pacman"):
        return "pacman -S --needed --noconfirm gpu-screen-recorder ffmpeg wl-clipboard curl"
    if shutil.which("dnf"):
        return "dnf install -y gpu-screen-recorder ffmpeg wl-clipboard curl"
    if shutil.which("apt-get"):
        return "apt-get update && apt-get install -y ffmpeg wl-clipboard curl"
    if shutil.which("zypper"):
        return "zypper install -y gpu-screen-recorder ffmpeg wl-clipboard curl"
    return "flatpak install -y flathub com.dec05eba.gpu_screen_recorder"


CSS = b"""
window, dialog {
    background-color: #0f1115;
    color: #eceef2;
}
.card {
    background-color: #181b22;
    border: 1px solid #262a34;
    border-radius: 10px;
    padding: 12px;
}
.title-header {
    font-size: 16px;
    font-weight: 700;
    color: #ffffff;
}
.section-title {
    font-size: 12px;
    font-weight: 600;
    color: #cbd5e1;
}
.muted {
    font-size: 12px;
    color: #94a3b8;
}
.status-bar {
    background-color: #12141a;
    border: 1px solid #262a34;
    border-radius: 8px;
    padding: 8px 12px;
    color: #a5b4fc;
}
entry, combobox button {
    background-color: #12141a;
    color: #eceef2;
    border: 1px solid #262a34;
    border-radius: 7px;
    padding: 5px 8px;
}
.btn-primary {
    background-image: none;
    background-color: #5865F2;
    color: #ffffff;
    font-weight: 600;
    border-radius: 7px;
    padding: 7px 14px;
    border: 1px solid #6875f5;
}
.btn-danger {
    background-image: none;
    background-color: #e11d48;
    color: #ffffff;
    font-weight: 600;
    border-radius: 7px;
    padding: 7px 14px;
    border: none;
}
.btn-secondary {
    background-image: none;
    background-color: #12141a;
    color: #d1d5db;
    font-weight: 500;
    border-radius: 7px;
    padding: 5px 10px;
    border: 1px solid #262a34;
}
.game-badge {
    background-color: #1e2230;
    color: #a5b4fc;
    border: 1px solid #374151;
    border-radius: 5px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
}
.clip-row {
    background-color: #12141a;
    border: 1px solid #262a34;
    border-radius: 7px;
    padding: 7px 10px;
    margin-bottom: 4px;
}
"""


class NullClipsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title=f"null-clips v{APP_VERSION}")
        self.set_wmclass("null-clips", "null-clips")
        self.set_default_size(720, 520)
        self.set_border_width(12)
        self.set_position(Gtk.WindowPosition.CENTER)

        settings = Gtk.Settings.get_default()
        if settings:
            settings.set_property("gtk-application-prefer-dark-theme", True)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.cfg = load_settings()
        self.output_dir = Path(self.cfg["outputDir"]).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cleanup_disk_replay_junk(self.output_dir)

        self.shared_links = load_json_dict(LINKS_PATH)
        self.clip_tags = load_json_dict(TAGS_PATH)
        self.selected_game_filter = "ALL"
        self._updating_filter_combo = False
        self.uploading_files = set()
        self.running = True
        self.closing_to_bg = False

        self.connect("delete-event", self.on_window_delete)
        self.connect("destroy", self.on_window_destroy)
        self.connect("key-press-event", self.on_key_press)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add(root)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_lbl = Gtk.Label(label=f"null-clips v{APP_VERSION} · Lite")
        title_lbl.get_style_context().add_class("title-header")
        header.pack_start(title_lbl, False, False, 0)

        quit_btn = Gtk.Button(label="Quit & Stop All")
        quit_btn.get_style_context().add_class("btn-danger")
        quit_btn.connect("clicked", self.on_quit_all)
        header.pack_end(quit_btn, False, False, 0)

        open_btn = Gtk.Button(label="Open Folder")
        open_btn.get_style_context().add_class("btn-secondary")
        open_btn.connect("clicked", lambda *_: subprocess.Popen(["xdg-open", str(self.output_dir)]))
        header.pack_end(open_btn, False, False, 0)

        if not shutil.which("gpu-screen-recorder") or not shutil.which("ffmpeg"):
            deps_btn = Gtk.Button(label="Install Dependencies")
            deps_btn.get_style_context().add_class("btn-primary")
            deps_btn.connect("clicked", self.on_install_deps)
            header.pack_end(deps_btn, False, False, 0)

        root.pack_start(header, False, False, 0)

        # Settings Card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class("card")

        # Folder row
        f_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        f_lbl = Gtk.Label(label="Clips Folder:")
        f_lbl.get_style_context().add_class("muted")
        f_row.pack_start(f_lbl, False, False, 0)

        self.folder_entry = Gtk.Entry()
        self.folder_entry.set_text(str(self.output_dir))
        f_row.pack_start(self.folder_entry, True, True, 0)

        browse_btn = Gtk.Button(label="Browse")
        browse_btn.get_style_context().add_class("btn-secondary")
        browse_btn.connect("clicked", self.on_browse_folder)
        f_row.pack_start(browse_btn, False, False, 0)

        apply_btn = Gtk.Button(label="Set")
        apply_btn.get_style_context().add_class("btn-secondary")
        apply_btn.connect("clicked", self.on_apply_folder)
        f_row.pack_start(apply_btn, False, False, 0)
        card.pack_start(f_row, False, False, 0)

        # Capture parameters row
        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        opts.pack_start(self._muted_label("Length:"), False, False, 0)
        self.sec_combo = Gtk.ComboBoxText()
        for s in ("15", "30", "60"):
            self.sec_combo.append(s, f"{s}s")
        self.sec_combo.set_active_id(str(self.cfg["seconds"]))
        self.sec_combo.connect("changed", self.on_setting_changed)
        opts.pack_start(self.sec_combo, False, False, 0)

        opts.pack_start(self._muted_label("Quality:"), False, False, 0)
        self.res_combo = Gtk.ComboBoxText()
        self.res_combo.append("1280x720", "720p (Ultra-Low RAM)")
        self.res_combo.append("1920x1080", "1080p")
        self.res_combo.set_active_id(str(self.cfg["resolution"]))
        self.res_combo.connect("changed", self.on_setting_changed)
        opts.pack_start(self.res_combo, False, False, 0)

        opts.pack_start(self._muted_label("FPS:"), False, False, 0)
        self.fps_combo = Gtk.ComboBoxText()
        self.fps_combo.append("30", "30")
        self.fps_combo.append("60", "60")
        self.fps_combo.set_active_id(str(self.cfg["fps"]))
        self.fps_combo.connect("changed", self.on_setting_changed)
        opts.pack_start(self.fps_combo, False, False, 0)

        opts.pack_start(self._muted_label("Hotkey:"), False, False, 0)
        self.hk_combo = Gtk.ComboBoxText()
        for k in ("F8", "F9", "F10", "F12", "Insert"):
            self.hk_combo.append(k, k)
        self.hk_combo.set_active_id(str(self.cfg["hotkey"]))
        self.hk_combo.connect("changed", self.on_setting_changed)
        opts.pack_start(self.hk_combo, False, False, 0)

        card.pack_start(opts, False, False, 0)

        # Audio row
        audio_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.desk_check = Gtk.CheckButton(label="Desktop Audio")
        self.desk_check.set_active(bool(self.cfg["desktopAudio"]))
        self.desk_check.connect("toggled", self.on_setting_changed)
        audio_row.pack_start(self.desk_check, False, False, 0)

        self.mic_check = Gtk.CheckButton(label="Mic Audio:")
        self.mic_check.set_active(bool(self.cfg["includeMic"]))
        self.mic_check.connect("toggled", self.on_setting_changed)
        audio_row.pack_start(self.mic_check, False, False, 0)

        self.mic_combo = Gtk.ComboBoxText()
        mics = list_microphone_devices()
        valid_mics = set()
        for dev_id, label in mics:
            self.mic_combo.append(dev_id, label)
            valid_mics.add(dev_id)
        active_mic = str(self.cfg["micDevice"]) if str(self.cfg["micDevice"]) in valid_mics else "default_input"
        self.mic_combo.set_active_id(active_mic)
        self.mic_combo.connect("changed", self.on_setting_changed)
        audio_row.pack_start(self.mic_combo, True, True, 0)

        card.pack_start(audio_row, False, False, 0)

        # Checkboxes row 1
        toggles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.bg_check = Gtk.CheckButton(label="Keep Running When Closed (0.8 MB C Daemon)")
        self.bg_check.set_active(bool(self.cfg["keepRunningClosed"]))
        self.bg_check.connect("toggled", self.on_setting_changed)
        toggles.pack_start(self.bg_check, False, False, 0)

        self.boot_check = Gtk.CheckButton(label="Start on Boot")
        self.boot_check.set_active(bool(self.cfg["startOnBoot"]))
        self.boot_check.connect("toggled", self.on_boot_toggled)
        toggles.pack_start(self.boot_check, False, False, 0)

        self.sound_check = Gtk.CheckButton(label="Sound Chime")
        self.sound_check.set_active(bool(self.cfg["soundEnabled"]))
        self.sound_check.connect("toggled", self.on_setting_changed)
        toggles.pack_start(self.sound_check, False, False, 0)

        self.osd_check = Gtk.CheckButton(label="OSD Toast")
        self.osd_check.set_active(bool(self.cfg.get("osdNotifications", True)))
        self.osd_check.connect("toggled", self.on_setting_changed)
        toggles.pack_start(self.osd_check, False, False, 0)

        card.pack_start(toggles, False, False, 0)

        # Checkboxes row 2 (Debloated Game-Only Buffer, Auto-Rename by Game, Auto-Discord Link, Folder Cap)
        toggles2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.game_only_check = Gtk.CheckButton(label="Game-Only Buffer (Optional)")
        self.game_only_check.set_tooltip_text(
            "Optional (Off by default): When checked, pauses gpu-screen-recorder on the desktop (0 MB RAM) and only buffers while a game or Steam/Proton is running."
        )
        self.game_only_check.set_active(bool(self.cfg.get("gameOnlyBuffer", False)))
        self.game_only_check.connect("toggled", self.on_setting_changed)
        toggles2.pack_start(self.game_only_check, False, False, 0)

        self.rename_game_check = Gtk.CheckButton(label="Auto-Name by Game")
        self.rename_game_check.set_tooltip_text(
            "Automatically prefixes saved MP4 filenames with the active game name (e.g. CS2_2025-05-12.mp4)."
        )
        self.rename_game_check.set_active(bool(self.cfg.get("autoRenameWithGame", True)))
        self.rename_game_check.connect("toggled", self.on_setting_changed)
        toggles2.pack_start(self.rename_game_check, False, False, 0)

        self.discord_check = Gtk.CheckButton(label="Auto-Discord Link")
        self.discord_check.set_tooltip_text(
            "Automatically uploads newly saved clips and copies an inline-embeddable MP4 link to your clipboard."
        )
        self.discord_check.set_active(bool(self.cfg["autoShareDiscord"]))
        self.discord_check.connect("toggled", self.on_setting_changed)
        toggles2.pack_start(self.discord_check, False, False, 0)

        toggles2.pack_start(self._muted_label("Cap:"), False, False, 0)
        self.cap_combo = Gtk.ComboBoxText()
        for cap_id, cap_lbl in (("0", "Off"), ("5", "5 GB"), ("10", "10 GB"), ("25", "25 GB")):
            self.cap_combo.append(cap_id, cap_lbl)
        self.cap_combo.set_tooltip_text(
            "Optional (Off by default): Automatically deletes the oldest saved clips only when the folder exceeds this size."
        )
        self.cap_combo.set_active_id(str(self.cfg.get("folderSizeCapGb", "0")))
        self.cap_combo.connect("changed", self.on_setting_changed)
        toggles2.pack_start(self.cap_combo, False, False, 0)

        card.pack_start(toggles2, False, False, 0)

        # Action Buttons
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.start_btn = Gtk.Button(label="Start Replay Buffer")
        self.start_btn.get_style_context().add_class("btn-primary")
        self.start_btn.connect("clicked", self.on_start_buffer)
        btn_row.pack_start(self.start_btn, True, True, 0)

        self.save_btn = Gtk.Button(label="Save Last 30s Clip")
        self.save_btn.get_style_context().add_class("btn-primary")
        self.save_btn.connect("clicked", self.on_save_clip)
        self.save_btn.set_no_show_all(True)
        btn_row.pack_start(self.save_btn, True, True, 0)

        self.stop_btn = Gtk.Button(label="Stop Buffer")
        self.stop_btn.get_style_context().add_class("btn-danger")
        self.stop_btn.connect("clicked", self.on_stop_buffer)
        self.stop_btn.set_no_show_all(True)
        btn_row.pack_start(self.stop_btn, False, False, 0)

        if not self._has_readable_input() and not (
            os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or os.environ.get("SWAYSOCK")
        ):
            unlock_btn = Gtk.Button(label="Unlock Hotkey")
            unlock_btn.get_style_context().add_class("btn-secondary")
            unlock_btn.connect("clicked", self.on_unlock_hotkey)
            btn_row.pack_start(unlock_btn, False, False, 0)

        card.pack_start(btn_row, False, False, 0)

        self.status_lbl = Gtk.Label(label="Ready.")
        self.status_lbl.get_style_context().add_class("status-bar")
        self.status_lbl.set_halign(Gtk.Align.FILL)
        self.status_lbl.set_xalign(0.0)
        self.status_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        card.pack_start(self.status_lbl, False, False, 0)

        root.pack_start(card, False, False, 0)

        # Clips List Card
        clips_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        clips_card.get_style_context().add_class("card")

        c_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.clips_title = Gtk.Label(label="Recent Clips")
        self.clips_title.get_style_context().add_class("section-title")
        self.clips_title.set_halign(Gtk.Align.START)
        c_head.pack_start(self.clips_title, True, True, 0)

        c_head.pack_start(self._muted_label("Game:"), False, False, 0)
        self.game_filter_combo = Gtk.ComboBoxText()
        self.game_filter_combo.append("ALL", "All Games")
        self.game_filter_combo.set_active_id("ALL")
        self.game_filter_combo.connect("changed", self.on_game_filter_changed)
        c_head.pack_start(self.game_filter_combo, False, False, 0)

        ref_btn = Gtk.Button(label="Refresh")
        ref_btn.get_style_context().add_class("btn-secondary")
        ref_btn.connect("clicked", lambda *_: self.refresh_clips())
        c_head.pack_start(ref_btn, False, False, 0)
        clips_card.pack_start(c_head, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(185)
        self.clips_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroll.add(self.clips_box)
        clips_card.pack_start(scroll, True, True, 0)

        root.pack_start(clips_card, True, True, 0)

        register_compositor_shortcut(str(self.cfg["hotkey"]))
        threading.Thread(target=ensure_c_daemon_binary, daemon=True).start()
        self.start_evdev_thread()
        GLib.timeout_add_seconds(4, self.on_game_only_tick)
        self.sync_ui_state()
        self.refresh_clips()

    def on_game_only_tick(self):
        if not self.running:
            return False
        if self.cfg.get("gameOnlyBuffer", False) and shutil.which("gpu-screen-recorder"):
            active_game = detect_active_game()
            alive = get_running_gsr_pid() > 0
            if active_game != "Desktop" and not alive:
                start_gsr_replay_buffer(self.cfg, prefer_direct_screen=True)
                self.sync_ui_state()
                self.set_status(f"Game detected ({active_game}) — Auto-started {self.cfg.get('seconds', '30')}s Replay Buffer.")
            elif active_game == "Desktop" and alive:
                stop_all_gsr_processes()
                self.sync_ui_state()
                self.set_status("No active game — Replay Buffer auto-paused (0 MB RAM / 0% GPU).")
        return True

    def _muted_label(self, text: str):
        lbl = Gtk.Label(label=text)
        lbl.get_style_context().add_class("muted")
        return lbl

    def _has_readable_input(self) -> bool:
        return any(os.access(p, os.R_OK) for p in glob.glob("/dev/input/event*"))

    def set_status(self, msg: str):
        GLib.idle_add(self.status_lbl.set_text, msg)

    def copy_to_all_clipboards(self, text: str):
        copy_text_system_clipboard(text)
        try:
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_text(text, -1)
            cb.store()
        except Exception:
            pass
        try:
            pb = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
            pb.set_text(text, -1)
        except Exception:
            pass

    def sync_ui_state(self):
        alive = get_running_gsr_pid() > 0
        sec = self.sec_combo.get_active_id() or "30"
        hk = self.hk_combo.get_active_id() or "F8"
        if alive:
            self.start_btn.hide()
            self.save_btn.set_label(f"Save Last {sec}s Clip ({hk})")
            self.save_btn.show()
            self.stop_btn.show()
            self.status_lbl.set_text(
                f"Replay Buffer Active ({sec}s, inotify ready) — Press {hk} in-game or close window for 0.8 MB C daemon."
            )
        else:
            self.start_btn.set_label(f"Start {sec}s Replay Buffer")
            self.start_btn.show()
            self.save_btn.hide()
            self.stop_btn.hide()
            if self.cfg.get("gameOnlyBuffer", False):
                self.status_lbl.set_text(
                    "Game-Only Buffer Standby (0 MB RAM / 0% GPU) — Will auto-start when a game launches."
                )

    def on_setting_changed(self, *_args):
        self.cfg["seconds"] = self.sec_combo.get_active_id() or "30"
        self.cfg["resolution"] = self.res_combo.get_active_id() or "1280x720"
        self.cfg["fps"] = self.fps_combo.get_active_id() or "60"
        self.cfg["hotkey"] = self.hk_combo.get_active_id() or "F8"
        self.cfg["desktopAudio"] = self.desk_check.get_active()
        self.cfg["includeMic"] = self.mic_check.get_active()
        self.cfg["micDevice"] = self.mic_combo.get_active_id() or "default_input"
        self.cfg["keepRunningClosed"] = self.bg_check.get_active()
        self.cfg["soundEnabled"] = self.sound_check.get_active()
        self.cfg["osdNotifications"] = self.osd_check.get_active()
        self.cfg["gameOnlyBuffer"] = self.game_only_check.get_active()
        self.cfg["autoRenameWithGame"] = self.rename_game_check.get_active()
        self.cfg["autoShareDiscord"] = self.discord_check.get_active()
        self.cfg["folderSizeCapGb"] = self.cap_combo.get_active_id() or "0"
        save_settings(self.cfg)
        register_compositor_shortcut(self.cfg["hotkey"])
        self.sync_ui_state()

    def on_boot_toggled(self, *_args):
        self.cfg["startOnBoot"] = self.boot_check.get_active()
        save_settings(self.cfg)
        self.set_status(configure_autostart(self.cfg["startOnBoot"]))

    def on_game_filter_changed(self, combo):
        if self._updating_filter_combo:
            return
        self.selected_game_filter = combo.get_active_id() or "ALL"
        self.refresh_clips()

    def on_browse_folder(self, _btn):
        dlg = Gtk.FileChooserDialog(
            title="Select Clips Folder",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            "Select",
            Gtk.ResponseType.OK,
        )
        dlg.set_current_folder(str(self.output_dir))
        if dlg.run() == Gtk.ResponseType.OK:
            self.folder_entry.set_text(dlg.get_filename())
            self.on_apply_folder(None)
        dlg.destroy()

    def on_apply_folder(self, _btn):
        raw = self.folder_entry.get_text().strip()
        if not raw:
            return
        try:
            p = Path(raw).expanduser().resolve()
            p.mkdir(parents=True, exist_ok=True)
            self.output_dir = p
            self.cfg["outputDir"] = str(p)
            save_settings(self.cfg)
            self.refresh_clips()
            self.set_status(f"Clips folder set to {p}")
        except Exception as e:
            self.set_status(f"Folder error: {e}")

    def on_start_buffer(self, _btn=None):
        if not shutil.which("gpu-screen-recorder"):
            self.set_status("gpu-screen-recorder missing — click 'Install Dependencies' above.")
            return
        self.on_setting_changed()
        pid = start_gsr_replay_buffer(self.cfg, prefer_direct_screen=False)
        self.sync_ui_state()
        if pid <= 0:
            self.set_status("Failed to start gpu-screen-recorder.")

    def on_stop_buffer(self, _btn=None):
        stop_all_gsr_processes()
        self.sync_ui_state()
        self.set_status("Replay Buffer stopped.")
        GLib.timeout_add(500, self.refresh_clips)

    def on_save_clip(self, _btn=None):
        if get_running_gsr_pid() <= 0:
            self.set_status("Start Replay Buffer first.")
            return
        sec = int(self.cfg.get("seconds", "30"))
        self.set_status(f"Saving last {sec}s clip...")

        def worker():
            newest = save_replay_clip_file(self.cfg)
            GLib.idle_add(self.on_clip_saved_ui, newest, sec)

        threading.Thread(target=worker, daemon=True).start()

    def on_clip_saved_ui(self, newest, sec: int):
        self.clip_tags = load_json_dict(TAGS_PATH)
        self.shared_links = load_json_dict(LINKS_PATH)
        self.refresh_clips()
        if newest and newest.exists():
            dur = probe_duration_seconds(newest)
            game = get_clip_tag(self.clip_tags, newest)
            if self.cfg.get("autoShareDiscord", False):
                self.set_status(f"Saved [{game}] {newest.name} ({dur:.1f}s) — Auto-uploading Discord link...")
                self.on_share_clip(newest, is_auto=True)
            else:
                self.set_status(f"Saved [{game}] {newest.name} ({dur:.1f}s)")
        else:
            self.set_status(f"Saved {sec}s clip to {self.output_dir}")
        return False

    def on_edit_tag(self, file_path: Path):
        current_tag = get_clip_tag(self.clip_tags, file_path)
        dlg = Gtk.Dialog(
            title=f"Tag Game — {file_path.name}",
            transient_for=self,
            flags=0,
        )
        dlg.add_buttons(
            Gtk.STOCK_CANCEL,
            Gtk.ResponseType.CANCEL,
            "Save Tag",
            Gtk.ResponseType.OK,
        )
        dlg.set_default_size(340, 140)
        box = dlg.get_content_area()
        box.set_spacing(8)
        box.set_border_width(12)

        preset_lbl = self._muted_label("Quick Select Preset:")
        preset_lbl.set_halign(Gtk.Align.START)
        box.pack_start(preset_lbl, False, False, 0)

        preset_combo = Gtk.ComboBoxText()
        preset_combo.append("", "Choose a game preset...")
        for g in PRESET_GAME_TAGS:
            preset_combo.append(g, g)
        box.pack_start(preset_combo, False, False, 0)

        custom_lbl = self._muted_label("Or Enter Custom Game Name:")
        custom_lbl.set_halign(Gtk.Align.START)
        box.pack_start(custom_lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(current_tag)
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        def on_preset_picked(combo):
            val = combo.get_active_id()
            if val:
                entry.set_text(val)

        preset_combo.connect("changed", on_preset_picked)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            new_tag = entry.get_text().strip() or "Desktop"
            set_clip_tag(file_path, new_tag)
            self.clip_tags = load_json_dict(TAGS_PATH)
            self.refresh_clips()
            self.set_status(f"Tagged {file_path.name} as [{new_tag}]")
        dlg.destroy()

    def on_unlock_hotkey(self, _btn):
        user = os.environ.get("USER", "")
        cmd = f"chmod a+r /dev/input/event*; usermod -aG input {user} || true"
        if subprocess.run(["pkexec", "sh", "-c", cmd], check=False).returncode == 0:
            self.start_evdev_thread()
            self.set_status("Global hotkey unlocked!")

    def on_install_deps(self, _btn):
        user = os.environ.get("USER", "")
        cmd = f"{detect_distro_install_cmd()}; chmod a+r /dev/input/event* || true; usermod -aG input {user} || true"
        self.set_status("Installing dependencies...")
        threading.Thread(
            target=lambda: subprocess.run(["pkexec", "sh", "-c", cmd], check=False),
            daemon=True,
        ).start()

    def start_evdev_thread(self):
        event_struct = struct.Struct("llHHi")
        files = []
        for path in glob.glob("/dev/input/event*"):
            if os.access(path, os.R_OK):
                try:
                    files.append(open(path, "rb", buffering=0))
                except Exception:
                    pass
        if not files:
            return

        def loop():
            last_trigger = 0.0
            while self.running:
                try:
                    rlist, _, _ = select.select(files, [], [], 0.8)
                    for f in rlist:
                        data = f.read(event_struct.size)
                        if data and len(data) == event_struct.size:
                            _s, _u, ev_type, ev_code, ev_val = event_struct.unpack(data)
                            target = KEYCODE_MAP.get(self.cfg.get("hotkey", "F8"), 66)
                            if ev_type == EV_KEY and ev_code == target and ev_val == 1:
                                now = time.time()
                                if now - last_trigger > 1.5:
                                    last_trigger = now
                                    GLib.idle_add(self.on_save_clip)
                except Exception:
                    break
            for f in files:
                try:
                    f.close()
                except Exception:
                    pass

        threading.Thread(target=loop, daemon=True).start()

    def on_key_press(self, _widget, event):
        keyname = Gdk.keyval_name(event.keyval)
        if keyname and keyname.lower() == str(self.cfg.get("hotkey", "F8")).lower():
            if get_running_gsr_pid() > 0:
                self.on_save_clip()
            return True
        return False

    def _update_game_filter_options(self, all_files: list):
        self._updating_filter_combo = True
        try:
            games = sorted({get_clip_tag(self.clip_tags, f) for f in all_files})
            self.game_filter_combo.remove_all()
            self.game_filter_combo.append("ALL", "All Games")
            for g in games:
                self.game_filter_combo.append(g, g)
            if self.selected_game_filter != "ALL" and self.selected_game_filter in games:
                self.game_filter_combo.set_active_id(self.selected_game_filter)
            else:
                self.selected_game_filter = "ALL"
                self.game_filter_combo.set_active_id("ALL")
        finally:
            self._updating_filter_combo = False

    def refresh_clips(self):
        self.shared_links = load_json_dict(LINKS_PATH)
        self.clip_tags = load_json_dict(TAGS_PATH)

        for child in self.clips_box.get_children():
            self.clips_box.remove(child)

        all_files = get_clip_files(self.output_dir)
        self._update_game_filter_options(all_files)

        if self.selected_game_filter == "ALL":
            files = all_files
        else:
            files = [f for f in all_files if get_clip_tag(self.clip_tags, f) == self.selected_game_filter]

        self.clips_title.set_text(f"Recent Clips ({len(files)})")

        if not files:
            empty = self._muted_label(f"No clips found in {self.output_dir}")
            self.clips_box.pack_start(empty, False, False, 8)
        else:
            pending_thumbs = []
            for f in files[:15]:
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.get_style_context().add_class("clip-row")

                thumb_img = Gtk.Image()
                thumb_img.set_size_request(64, 36)
                t_path = get_thumb_cache_path(f)
                if t_path.exists():
                    try:
                        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(t_path), 64, 36, False)
                        thumb_img.set_from_pixbuf(pix)
                    except Exception:
                        pass
                else:
                    pending_thumbs.append((f, t_path, thumb_img))
                row.pack_start(thumb_img, False, False, 0)

                game_name = get_clip_tag(self.clip_tags, f)
                badge = Gtk.Label(label=game_name)
                badge.get_style_context().add_class("game-badge")
                row.pack_start(badge, False, False, 0)

                size_mb = f.stat().st_size / (1024 * 1024)
                key = str(f)
                existing_url = self.shared_links.get(key) or self.shared_links.get(f.name)
                lbl = Gtk.Label(label=f"{f.name}  ·  {size_mb:.1f} MB")
                lbl.set_halign(Gtk.Align.START)
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                row.pack_start(lbl, True, True, 0)

                tag_btn = Gtk.Button(label="Tag")
                tag_btn.get_style_context().add_class("btn-secondary")
                tag_btn.connect("clicked", lambda _b, p=f: self.on_edit_tag(p))
                row.pack_start(tag_btn, False, False, 0)

                play_btn = Gtk.Button(label="Play")
                play_btn.get_style_context().add_class("btn-secondary")
                play_btn.connect("clicked", lambda _b, p=f: subprocess.Popen(["xdg-open", str(p)]))
                row.pack_start(play_btn, False, False, 0)

                share_lbl = (
                    "Uploading..."
                    if key in self.uploading_files
                    else ("Copy Link" if existing_url else "Discord Link")
                )
                share_btn = Gtk.Button(label=share_lbl)
                share_btn.get_style_context().add_class("btn-primary")
                share_btn.set_sensitive(key not in self.uploading_files)
                share_btn.connect("clicked", lambda _b, p=f: self.on_share_clip(p, is_auto=False))
                row.pack_start(share_btn, False, False, 0)

                del_btn = Gtk.Button(label="Delete")
                del_btn.get_style_context().add_class("btn-secondary")
                del_btn.connect("clicked", lambda _b, p=f: self.on_delete_clip(p))
                row.pack_start(del_btn, False, False, 0)

                self.clips_box.pack_start(row, False, False, 0)

            if pending_thumbs and shutil.which("ffmpeg"):
                threading.Thread(
                    target=self._generate_thumbs_worker,
                    args=(pending_thumbs,),
                    daemon=True,
                ).start()

        self.clips_box.show_all()
        return False

    def _generate_thumbs_worker(self, items: list):
        try:
            THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            return
        for video_path, thumb_path, img_widget in items:
            if not self.running:
                return
            if not thumb_path.exists():
                subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-ss",
                        "0.5",
                        "-i",
                        str(video_path),
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=64:36:force_original_aspect_ratio=increase,crop=64:36",
                        "-q:v",
                        "8",
                        str(thumb_path),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
            if thumb_path.exists():
                GLib.idle_add(self._apply_thumb_pixbuf, img_widget, thumb_path)

    def _apply_thumb_pixbuf(self, img_widget, thumb_path: Path):
        try:
            pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(thumb_path), 64, 36, False)
            img_widget.set_from_pixbuf(pix)
        except Exception:
            pass
        return False

    def on_share_clip(self, file_path: Path, is_auto: bool = False):
        key = str(file_path)
        existing_url = self.shared_links.get(key) or self.shared_links.get(file_path.name)
        if existing_url and not is_auto:
            self.copy_to_all_clipboards(existing_url)
            self.set_status(f"Copied Discord link: {existing_url}")
            return

        if key in self.uploading_files:
            return

        self.uploading_files.add(key)
        self.refresh_clips()
        if not is_auto:
            self.set_status(f"Uploading {file_path.name} for Discord...")

        def worker():
            try:
                url = upload_mp4_for_discord(file_path)
                links = load_json_dict(LINKS_PATH)
                links[key] = url
                links[file_path.name] = url
                save_json_dict(LINKS_PATH, links)
                GLib.idle_add(self.on_upload_done, key, url, None, is_auto)
            except Exception as e:
                GLib.idle_add(self.on_upload_done, key, None, str(e), is_auto)

        threading.Thread(target=worker, daemon=True).start()

    def on_upload_done(self, key: str, url, err, is_auto: bool = False):
        self.uploading_files.discard(key)
        self.shared_links = load_json_dict(LINKS_PATH)
        if url:
            self.copy_to_all_clipboards(url)
            prefix = "Auto-Copied Discord Link" if is_auto else "Copied Discord Link"
            self.set_status(f"{prefix}: {url}")
            if is_auto:
                send_desktop_notification(
                    "null-clips · Discord Link Copied",
                    url,
                    enabled=bool(self.cfg.get("osdNotifications", True)),
                )
        else:
            self.set_status(f"Discord link upload failed: {err}")
        self.refresh_clips()
        return False

    def on_delete_clip(self, file_path: Path):
        try:
            get_thumb_cache_path(file_path).unlink(missing_ok=True)
            file_path.unlink(missing_ok=True)
            self.refresh_clips()
            self.set_status(f"Deleted {file_path.name}")
        except Exception as e:
            self.set_status(f"Delete error: {e}")

    def on_window_delete(self, *_args):
        """
        When closed with Keep Running When Closed enabled:
        Exit the GTK3 GUI process completely (freeing 100% of GTK3 RAM) and spawn the ~0.8 MB C daemon
        (or Game-Only background watcher) if buffer or Game-Only mode is active.
        """
        self.running = False
        if self.cfg.get("keepRunningClosed", True) and (
            get_running_gsr_pid() > 0 or self.cfg.get("gameOnlyBuffer", False)
        ):
            self.closing_to_bg = True
            spawn_background_watcher(self.cfg)
        else:
            stop_all_gsr_processes()
        Gtk.main_quit()
        return False

    def on_window_destroy(self, *_args):
        self.running = False
        if not self.closing_to_bg and not self.cfg.get("keepRunningClosed", True):
            stop_all_gsr_processes()
        Gtk.main_quit()

    def on_quit_all(self, *_args):
        self.running = False
        self.closing_to_bg = False
        stop_background_daemon()
        stop_all_gsr_processes()
        Gtk.main_quit()


if __name__ == "__main__":
    win = NullClipsWindow()
    win.show_all()
    win.sync_ui_state()
    Gtk.main()
