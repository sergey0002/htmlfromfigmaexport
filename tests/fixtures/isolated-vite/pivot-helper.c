/* Synthetic namespace experiment only. No user paths are accepted by the wrapper. */
#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static void fail(const char *message) { perror(message); _exit(1); }
int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "missing root or command\n"); return 2; }
    if (mount(argv[1], argv[1], NULL, MS_BIND|MS_REC, NULL) < 0) fail("bind root");
    if (chdir(argv[1]) < 0) fail("chdir root");
    if (mkdir(".oldroot", 0700) < 0 && errno != EEXIST) fail("mkdir oldroot");
    if (syscall(SYS_pivot_root, ".", ".oldroot") < 0) fail("pivot_root");
    if (chdir("/") < 0) fail("chdir new root");
    if (umount2("/.oldroot", MNT_DETACH) < 0) fail("detach old root");
    if (rmdir("/.oldroot") < 0) fail("remove old root");
    execv(argv[2], argv+2);
    fail("exec after pivot");
}
