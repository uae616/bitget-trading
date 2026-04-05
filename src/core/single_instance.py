import atexit
import os
from pathlib import Path


class AlreadyRunningError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._fh = None
        self._locked = False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.lock_path, "a+", encoding="utf-8")

        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self._fh.close()
            self._fh = None
            raise AlreadyRunningError("Another instance is already running")

        self._locked = True
        self._fh.seek(0)
        self._fh.truncate(0)
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        atexit.register(self.release)

    def release(self) -> None:
        if not self._locked or self._fh is None:
            return

        try:
            if os.name == "nt":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            self._fh.close()
            self._fh = None


def acquire_single_instance_lock(lock_file: str = "state/bot.lock") -> SingleInstanceLock:
    lock = SingleInstanceLock(Path(lock_file))
    lock.acquire()
    return lock
