/* Synthetic-only bounded negative probes; not an aggregate resource controller. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static void fail(const char *why) { perror(why); exit(1); }
static void expect_limit(int type, rlim_t value) {
    struct rlimit got;
    if (getrlimit(type,&got) || got.rlim_cur!=value || got.rlim_max!=value) fail("fixture inherited rlimit");
}
int main(void) {
    expect_limit(RLIMIT_NOFILE,256); expect_limit(RLIMIT_FSIZE,33554432);
    expect_limit(RLIMIT_CPU,30); expect_limit(RLIMIT_AS,68719476736ULL); expect_limit(RLIMIT_CORE,0);
    struct rlimit hard={257,257};
    errno=0; if (setrlimit(RLIMIT_NOFILE,&hard)==0 || errno!=EPERM) fail("raising hard limit succeeded");
    int fds[512], count=0, fd;
    while ((fd=open("/dev/null",O_RDONLY|O_CLOEXEC))>=0) {
        if(count>=512) fail("too many fds");
        fds[count++]=fd;
    }
    if(errno!=EMFILE || count<100) fail("descriptor limit not enforced");
    for(int i=0;i<count;i++) if(close(fds[i])) fail("close descriptor");
    struct rlimit fs={1024,1024}; if(setrlimit(RLIMIT_FSIZE,&fs)) fail("lower file limit");
    if(signal(SIGXFSZ,SIG_IGN)==SIG_ERR) fail("signal");
    const char *name="/tmp/fixture-rlimit-probe";
    fd=open(name,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600); if(fd<0) fail("create bounded probe");
    errno=0; int result=ftruncate(fd,2048); int err=errno;
    if(close(fd) || unlink(name)) fail("cleanup bounded probe");
    if(result==0 || err!=EFBIG) {errno=err;fail("file size limit not enforced");}
    struct rlimit vm={64*1024*1024,64*1024*1024}; if(setrlimit(RLIMIT_AS,&vm)) fail("lower address-space limit");
    errno=0; void *p=mmap(NULL,128*1024*1024,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(p!=MAP_FAILED) {munmap(p,128*1024*1024); fail("address-space limit not enforced");}
    if(errno!=ENOMEM) fail("unexpected mmap error");
    pid_t child=fork(); if(child<0) fail("fork cpu probe");
    if(child==0) {
        struct rlimit cpu={1,1}; if(setrlimit(RLIMIT_CPU,&cpu)) _exit(2);
        volatile unsigned long n=0; for(;;) n++;
    }
    int status=0; if(waitpid(child,&status,0)!=child) fail("wait cpu probe");
    if(!WIFSIGNALED(status) || WTERMSIG(status)!=SIGKILL) {errno=0;fail("cpu limit not enforced");}
    puts("RESOURCE_PROBE_OK inherited hard limits, EMFILE, EFBIG, ENOMEM and CPU SIGKILL");
    return 0;
}
