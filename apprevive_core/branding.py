"""Compatibility with data created before the AppRevive rename."""
from functools import wraps
import os
from pathlib import Path

LEGACY_NAME = "AppRestore"
LEGACY_ENV_PREFIX = "APPRESTORE_"


def copy_legacy_environment() -> None:
    for key, value in list(os.environ.items()):
        if key.startswith(LEGACY_ENV_PREFIX):
            os.environ.setdefault("APPREVIVE_" + key[len(LEGACY_ENV_PREFIX):], value)


def legacy_directory_fallback(environment_key: str):
    """Existing users keep the same library, account cache and credit ledger.

    Keep the directory in place: moving it could break an installed venv's
    absolute paths. Fresh installations use AppRevive directories exclusively.
    Explicit environment overrides always take precedence.
    """
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs) -> Path:
            path = fn(*args, **kwargs)
            if os.environ.get(environment_key):
                return path
            for index in range(len(path.parts) - 1, -1, -1):
                part = path.parts[index]
                if part == "AppRevive":
                    legacy = Path(*path.parts[:index], LEGACY_NAME)
                    if legacy.is_dir():
                        return legacy.joinpath(*path.parts[index + 1:])
                    break
            return path
        return wrapped
    return decorate
