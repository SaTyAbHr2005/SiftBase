"""Build desktop/build/backend: a Python runtime, the pinned packages, the SiftBase code and the local models, so the
installed app needs nothing else on the PC. Run with the repo's Python 3.10 on Windows:

    python desktop/scripts/build_backend.py

Layout: python/ (official embeddable CPython), site-packages/, app/ (kb, scripts), models/ (fastembed cache).
"""
import hashlib
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

PY_VERSION = "3.10.11"  # last 3.10 release with a Windows build; same ABI (cp310) as the dev and CI Python
PY_URL = f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip"
PY_SHA256 = "608619f8619075629c9c69f361352a0da6ed7e62f83a0e19c63e0ea32eb7629d"  # first download over HTTPS from python.org
SKIP = {"pytest"}  # test-only requirements

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "desktop" / "build" / "backend"
CACHE = REPO / "desktop" / "build" / "cache"


def run(*cmd, **kw):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def python_runtime():
    CACHE.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE / Path(PY_URL).name
    if not zip_path.exists():
        print("downloading", PY_URL, flush=True)
        with urllib.request.urlopen(PY_URL) as r, open(zip_path, "wb") as f:
            shutil.copyfileobj(r, f)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print("sha256", digest)
    if PY_SHA256 and digest != PY_SHA256:
        sys.exit(f"{zip_path.name}: sha256 {digest} does not match the pinned {PY_SHA256}")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(OUT / "python")
    # The embeddable runtime ignores PYTHONPATH; its ._pth file is the whole import path.
    pth = next((OUT / "python").glob("python3*._pth"))
    zipname = next((OUT / "python").glob("python3*.zip")).name
    pth.write_text(f"{zipname}\n.\n../site-packages\n../app\nimport site\n", encoding="utf-8")


def packages():
    reqs = [line for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#") and line.split("==")[0].strip().lower() not in SKIP]
    req_file = CACHE / "requirements.bundle.txt"
    req_file.write_text("\n".join(reqs) + "\n", encoding="utf-8")
    run(sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check", "--no-compile",
        "--target", OUT / "site-packages", "-r", req_file)


def code():
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
    for name in ("kb", "scripts"):
        shutil.copytree(REPO / name, OUT / "app" / name, ignore=ignore)


def models():
    env = {**os.environ, "FASTEMBED_CACHE_PATH": str(OUT / "models"), "KB_ENV_FILE": str(CACHE / "no.env")}
    run(OUT / "python" / "python.exe", OUT / "app" / "scripts" / "prefetch_models.py", env=env, cwd=OUT / "app")


if __name__ == "__main__":
    if sys.platform != "win32" or sys.version_info[:2] != (3, 10):
        sys.exit("Build on Windows with Python 3.10, so the packages match the bundled runtime.")
    shutil.rmtree(OUT, ignore_errors=True)
    python_runtime()
    packages()
    code()
    models()
    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"backend ready: {OUT} ({size / 1e6:.0f} MB)")
