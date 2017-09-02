from contextlib import contextmanager
import os


@contextmanager
def nonroot(uid=None, gid=None):
    """
    Context manager that runs code as non-root.

    uid and gid are numeric, and if None they default to $SUDO_UID and
    $SUDO_GID from the environment
    """
    changed_gid = False
    if os.getgid() == 0:
        if gid is None:
            gid = int(os.environ["SUDO_GID"])
        os.setegid(gid)
        changed_gid = True

    changed_uid = False
    if os.getuid() == 0:
        if uid is None:
            uid = int(os.environ["SUDO_UID"])
        os.seteuid(uid)
        changed_uid = True

    yield

    if changed_uid:
        os.setuid(0)

    if changed_gid:
        os.setgid(0)


def preexec_nonroot(self, uid=None, gid=None):
    """
    Use as preexec_fn in subprocess.Popen to drop root and run with the given
    uid and gid.

    uid and gid are numeric, and if None they default to $SUDO_UID and
    $SUDO_GID from the environment

    Note that subprocess.Popen does not pass arguments to preexec_fn: use
    functools.partialmethod if you need to pass uid and gid.
    """
    if os.getgid() == 0:
        if gid is None:
            gid = int(os.environ["SUDO_GID"])
        os.setgid(int(os.environ["SUDO_GID"]))

    if os.getuid() == 0:
        if uid is None:
            uid = int(os.environ["SUDO_UID"])
        os.setuid(int(os.environ["SUDO_UID"]))

