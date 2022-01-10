#include <dlfcn.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

int main(int argc, char *argv[])
{
    if (argc != 2) {
        fprintf(stdout, "usage: %s so_path\n", argv[0]);
        return 0;
    }

    const char *dlname = argv[1];
    void *dlib = dlopen(dlname, RTLD_NOW | RTLD_GLOBAL);
    if (dlib != NULL) {
        fprintf(stdout, "Load successfully: %s\n", dlname);
        dlclose(dlib);
    } else {
        fprintf(stderr, "Load failed: %s, errno: %d - %s\n", dlname, errno, strerror(errno));
    }
    return 0;
}
