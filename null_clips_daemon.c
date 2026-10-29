// null-clips-daemon.c — Ultra-Lightweight Native Linux Hotkey & Replay Watcher (~0.8 MB RAM)
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
        fprintf(stderr, "Usage: %s <keycode> <null-clips-exe> [pid-file]\n", argv[0]);
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
            fprintf(fp, "%d\n", (int)getpid());
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
}
