"""Explicit local cleanup; never follows directory links or removes arbitrary imports."""
from pathlib import Path
import os

from apprevive_gui.account_bindings import bindings_path
from apprevive_gui.account_vault import live_dir, vault_root, _FILES
from apprevive_core.purchases_cache import forget_purchases_cache


def _linked(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def _remove_tree(path: Path) -> None:
    if _linked(path):
        path.unlink()
    elif path.is_dir():
        for child in path.iterdir():
            _remove_tree(child)
        path.rmdir()
    elif path.exists():
        path.unlink()


def clear_accounts() -> None:
    # Only known credential stores. Preserve promo balance, API config and icons.
    _remove_tree(vault_root())
    bindings_path().unlink(missing_ok=True)
    for name in _FILES:
        (live_dir() / name).unlink(missing_ok=True)
    forget_purchases_cache()


def clear_downloads(library: Path) -> int:
    """Remove IPA files only inside the configured AppRevive library.

    Do not traverse directory symlinks, or touch external IPA import locations.
    Leave unrelated documents and subdirectories intact.
    """
    library = Path(library)
    if _linked(library):
        raise OSError("Library is a symbolic link")
    if not library.exists():
        return 0
    count = 0
    for folder, dirs, files in os.walk(library, followlinks=False):
        dirs[:] = [d for d in dirs if not _linked(Path(folder) / d)]
        for name in files:
            if name.lower().endswith('.ipa'):
                (Path(folder) / name).unlink()
                count += 1
    return count
