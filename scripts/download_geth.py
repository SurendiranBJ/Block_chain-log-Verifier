"""
LogChain - Pinned Geth Downloader (v1.13.15)
=============================================
Clique Proof-of-Authority (PoA) consensus was deprecated and removed from upstream
go-ethereum (Geth) starting in v1.14.0 (post-Merge cleanup).

To ensure reproducible, zero-friction local multi-node PoA operation for LogChain,
this script automatically downloads and extracts the official pinned Geth v1.13.15
binary into the project's ./bin directory.

Supported platforms:
  - Windows (x86_64 / amd64) -> bin/geth.exe
  - Linux (x86_64 / amd64)   -> bin/geth
  - macOS (x86_64 & arm64)   -> bin/geth

Usage:
    python scripts/download_geth.py
    python scripts/download_geth.py --force
"""

import os
import sys
import platform
import shutil
import tarfile
import zipfile
import urllib.request
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BIN_DIR = _ROOT / "bin"

GETH_VERSION = "1.13.15"

DOWNLOAD_URLS = {
    ("windows", "amd64"): "https://gethstore.blob.core.windows.net/builds/geth-windows-amd64-1.13.15-c5ba367e.zip",
    ("windows", "x86_64"): "https://gethstore.blob.core.windows.net/builds/geth-windows-amd64-1.13.15-c5ba367e.zip",
    ("windows", "AMD64"): "https://gethstore.blob.core.windows.net/builds/geth-windows-amd64-1.13.15-c5ba367e.zip",
    ("linux", "x86_64"): "https://gethstore.blob.core.windows.net/builds/geth-linux-amd64-1.13.15-c5ba367e.tar.gz",
    ("linux", "amd64"): "https://gethstore.blob.core.windows.net/builds/geth-linux-amd64-1.13.15-c5ba367e.tar.gz",
    ("darwin", "x86_64"): "https://gethstore.blob.core.windows.net/builds/geth-darwin-amd64-1.13.15-c5ba367e.tar.gz",
    ("darwin", "amd64"): "https://gethstore.blob.core.windows.net/builds/geth-darwin-amd64-1.13.15-c5ba367e.tar.gz",
    ("darwin", "arm64"): "https://gethstore.blob.core.windows.net/builds/geth-darwin-arm64-1.13.15-c5ba367e.tar.gz",
}


def get_platform_key():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        norm_machine = "amd64"
    elif machine in ("arm64", "aarch64"):
        norm_machine = "arm64"
    else:
        norm_machine = machine
    return system, norm_machine


def get_target_binary_path():
    system = platform.system().lower()
    if system == "windows":
        return _BIN_DIR / "geth.exe"
    return _BIN_DIR / "geth"


def verify_binary(binary_path: Path):
    if not binary_path.exists():
        return False, "Binary file does not exist."
    try:
        res = subprocess.run(
            [str(binary_path), "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = res.stdout + res.stderr
        if f"1.13." in output:
            return True, output.strip().split("\n")[0]
        return False, f"Unexpected version output: {output.strip().split(chr(10))[0]}"
    except Exception as exc:
        return False, f"Execution failed: {exc}"


def download_and_extract(force: bool = False):
    print("=" * 60)
    print(" LogChain - Pinned Geth Installer (v1.13.15 for Clique PoA)")
    print("=" * 60)

    target_bin = get_target_binary_path()
    if target_bin.exists() and not force:
        ok, ver_str = verify_binary(target_bin)
        if ok:
            print(f"[PASS] Pinned Geth already installed at: {target_bin}")
            print(f"       {ver_str}")
            print("\nTo reinstall, run with --force")
            return target_bin

    sys_name, arch = get_platform_key()
    url = DOWNLOAD_URLS.get((sys_name, arch))
    if not url:
        # Fallback check
        for (k_sys, k_arch), candidate_url in DOWNLOAD_URLS.items():
            if k_sys == sys_name and k_arch in (arch, "amd64"):
                url = candidate_url
                break

    if not url:
        print(f"[FAIL] Unsupported platform: {sys_name} ({arch})")
        print(f"Please manually download Geth v1.13.15 from https://gethstore.blob.core.windows.net/builds/")
        print(f"and place the executable at: {target_bin}")
        sys.exit(1)

    _BIN_DIR.mkdir(parents=True, exist_ok=True)
    archive_name = url.split("/")[-1]
    temp_archive = _BIN_DIR / archive_name

    print(f"[*] Platform: {sys_name} ({arch})")
    print(f"[*] Downloading Geth v{GETH_VERSION} from official store...")
    print(f"    URL: {url}")

    def report_progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100.0, (downloaded / total_size) * 100)
            mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            sys.stdout.write(f"\r    Downloading: {pct:.1f}% ({mb:.1f} MB / {total_mb:.1f} MB)")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, temp_archive, reporthook=report_progress)
        print("\n[*] Download complete. Extracting binary...")
    except Exception as exc:
        print(f"\n[FAIL] Failed to download Geth archive: {exc}")
        sys.exit(1)

    # Extract binary from archive
    try:
        if archive_name.endswith(".zip"):
            with zipfile.ZipFile(temp_archive, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("geth.exe") or member == "geth.exe":
                        with zf.open(member) as source, open(target_bin, "wb") as target:
                            shutil.copyfileobj(source, target)
                        break
        elif archive_name.endswith((".tar.gz", ".tgz")):
            with tarfile.open(temp_archive, "r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("/geth") or member.name == "geth":
                        f = tf.extractfile(member)
                        if f:
                            with open(target_bin, "wb") as target:
                                shutil.copyfileobj(f, target)
                            break

        # Set executable permissions on Unix
        if sys_name != "windows":
            target_bin.chmod(0o755)

    except Exception as exc:
        print(f"[FAIL] Extraction failed: {exc}")
        if temp_archive.exists():
            temp_archive.unlink(missing_ok=True)
        sys.exit(1)
    finally:
        # Clean up temporary archive file
        if temp_archive.exists():
            temp_archive.unlink(missing_ok=True)

    ok, ver_str = verify_binary(target_bin)
    if ok:
        print(f"\n[PASS] Successfully installed Geth v{GETH_VERSION}!")
        print(f"       Location: {target_bin}")
        print(f"       Version:  {ver_str}")
        print("\nAll LogChain node starter and check scripts will now automatically prioritize this binary.")
        return target_bin
    else:
        print(f"\n[FAIL] Geth binary verification failed: {ver_str}")
        sys.exit(1)


if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    download_and_extract(force=force_flag)
