# core/staticfiles.py
"""
NpmBuildFinder: serves a pre-built frontend bundle (e.g. Vite/webpack
output) as a Django static finder, with an optional dev-only lazy build
for local convenience.

IMPORTANT: in any deployed environment, run `python manage.py build_frontend`
(see core/management/commands/build_frontend.py) as an explicit CI/deploy
step. Do NOT rely on lazy building in production — this finder's lazy-build
path is disabled unless NPM_BUILD_LAZY=True is explicitly set, and even
then is intended for local dev only.
"""
import os
import shutil
import subprocess
import threading
import logging
from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder
from django.core.exceptions import SuspiciousFileOperation

logger = logging.getLogger(__name__)

# Only ever build lazily from inside a request cycle if explicitly opted
# into (local dev). Defaults to DEBUG so it "just works" locally but is
# inert unless someone deliberately enables it in a non-debug environment.
NPM_BUILD_LAZY = getattr(settings, "NPM_BUILD_LAZY", settings.DEBUG)
NPM_BUILD_TIMEOUT = getattr(settings, "NPM_BUILD_TIMEOUT_SECONDS", 300)
# Cooldown before a failed build is retried, so one transient failure
# doesn't disable the finder for the life of the process.
NPM_BUILD_RETRY_COOLDOWN = getattr(settings, "NPM_BUILD_RETRY_COOLDOWN_SECONDS", 60)


def safe_join(base_dir: str, *paths: str) -> str:
    """
    Join path components onto base_dir and guarantee the result stays
    inside base_dir. Raises SuspiciousFileOperation on any attempt to
    escape via '..' segments or an absolute-path override (os.path.join
    silently discards `base_dir` if a later component is absolute, which
    is exactly the injection this guards against).
    """
    base_dir = os.path.realpath(base_dir)
    joined = os.path.realpath(os.path.join(base_dir, *paths))
    try:
        if os.path.commonpath([base_dir, joined]) != base_dir:
            raise SuspiciousFileOperation(
                f"Path traversal attempt: '{os.path.join(*paths)}' resolves outside base directory."
            )
    except ValueError:
        # commonpath raises ValueError on Windows if paths are on different drives
        raise SuspiciousFileOperation("Path traversal attempt: cross-drive path.")
    return joined

class NpmBuildFinder(BaseFinder):
    _build_lock = threading.Lock()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # The finder resolves incoming paths (e.g. "nexus_admin/assets/index.js")
        # against this root — it must be the PARENT of nexus_admin, since the
        # "nexus_admin/" segment is part of the path Django hands to find(),
        # not part of the finder's base directory.
        self.static_root = os.path.realpath(os.path.join(base_dir, "..", "static"))
        # Where the built frontend actually gets copied to by build_frontend().
        self.static_dir = os.path.join(self.static_root, "nexus_admin")
        self.frontend_dir = os.path.realpath(os.path.join(base_dir, "..", "..", "frontend"))
        self.dist_dir = os.path.join(self.frontend_dir, "dist")
        self._build_attempted = False
        self._build_success = False
        self._last_failure_time = None

    def find(self, path, all=False, **kwargs):
        try:
            full_path = safe_join(self.static_root, path)  # <-- static_root, not static_dir
        except SuspiciousFileOperation:
            logger.warning("Blocked path traversal attempt in static path: %r", path)
            return []

        if os.path.isfile(full_path):
            return [full_path] if all else full_path

        if not NPM_BUILD_LAZY:
            return []

        if self._should_attempt_build():
            self._trigger_build_once()
            if os.path.isfile(full_path):
                return [full_path] if all else full_path
            logger.warning("Build ran but %s still not found.", path)

        return []

    def list(self, ignore_patterns):
        """
        Required by collectstatic: yield (relative_path, storage) tuples
        for every file under static_dir. Without this, collectstatic
        crashes the moment it reaches this finder.
        """
        from django.contrib.staticfiles.storage import StaticFilesStorage
        from django.utils._os import safe_join as django_safe_join  # for storage init only

        if not os.path.isdir(self.static_dir):
            return

        storage = StaticFilesStorage(location=self.static_dir)
        for root, dirs, files in os.walk(self.static_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.static_dir)
                if ignore_patterns and any(
                    self._matches_pattern(rel_path, pat) for pat in ignore_patterns
                ):
                    continue
                yield rel_path, storage

    @staticmethod
    def _matches_pattern(path: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(path, pattern)

    def _should_attempt_build(self) -> bool:
        if self._build_success:
            return False
        if not self._build_attempted:
            return True
        if self._last_failure_time is None:
            return False
        import time
        return (time.monotonic() - self._last_failure_time) > NPM_BUILD_RETRY_COOLDOWN

    def _trigger_build_once(self):
        with self._build_lock:
            # Re-check inside the lock: another thread may have already
            # built (or failed-and-cooled-down-and-retried) while we waited.
            if self._build_success:
                return
            if self._build_attempted and not self._should_attempt_build():
                return

            self._build_attempted = True
            try:
                build_frontend(self.frontend_dir, self.dist_dir, self.static_dir)
                self._build_success = True
                self._last_failure_time = None
            except Exception as e:
                logger.error("Frontend build failed: %s", e)
                self._build_success = False
                import time
                self._last_failure_time = time.monotonic()

import shutil

def _npm_executable() -> str:
    """
    Resolves the correct npm invocation for the current platform.
    On Windows, npm ships as npm.cmd, which subprocess.run cannot
    execute directly without shell=True (CreateProcess only launches
    true executables, not batch scripts — cmd.exe is what knows how
    to resolve .cmd extensions). shutil.which() correctly finds
    npm.cmd on Windows and npm on POSIX, so use its resolved path
    rather than shelling out.
    """
    resolved = shutil.which("npm")
    if resolved is None:
        raise RuntimeError(
            "npm not found in PATH. Install Node.js or add it to PATH."
        )
    return resolved

def build_frontend(frontend_dir: str, dist_dir: str, static_dir: str):
    npm = _npm_executable()

    try:
        subprocess.run(
            [npm, "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=True,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("npm --version timed out — PATH or environment misconfigured.")

    try:
        subprocess.run(
            [npm, "run", "build"],
            cwd=frontend_dir,
            check=True,
            timeout=NPM_BUILD_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"npm run build exceeded {NPM_BUILD_TIMEOUT}s timeout.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"npm run build failed with exit code {e.returncode}.")

    if not os.path.isdir(dist_dir):
        raise RuntimeError(f"Build output {dist_dir} not found after build.")

    if os.path.isdir(static_dir):
        shutil.rmtree(static_dir)
    shutil.copytree(dist_dir, static_dir)
