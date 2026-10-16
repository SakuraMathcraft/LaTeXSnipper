#include <mach-o/dyld.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Keep the outer bundle entry point independent of Python and Qt. */
int main(int argc, char **argv) {
    char path[PATH_MAX], resolved[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0 || realpath(path, resolved) == NULL) return 1;
    char *directory = strrchr(resolved, '/');
    if (directory == NULL) return 1;
    *directory = '\0';
    const char *relative = "/../Resources/desktop/LaTeXSnipper";
    if (strlen(resolved) + strlen(relative) >= sizeof(resolved)) return 1;
    strcat(resolved, relative);
    argv[0] = resolved;
    execv(resolved, argv);
    return 1;
}
