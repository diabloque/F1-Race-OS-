"""Set up RaceOS locally, build its dashboard, and start one server."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def project_environment():
    env = os.environ.copy()
    for key, folder in {
        "TEMP": "tmp",
        "TMP": "tmp",
        "TMPDIR": "tmp",
        "PIP_CACHE_DIR": "cache/pip",
        "npm_config_cache": "cache/npm",
        "MPLCONFIGDIR": "cache/matplotlib",
    }.items():
        location = DATA / folder
        location.mkdir(parents=True, exist_ok=True)
        env[key] = str(location)
    env["PYTHONUNBUFFERED"] = "1"
    # Older bundled pip does not read the Windows certificate store itself.
    if os.name == "nt" and not env.get("PIP_CERT"):
        certificate_file = DATA / "tmp/system-ca.pem"
        certificates = ssl.create_default_context().get_ca_certs(binary_form=True)
        certificate_file.write_text(
            "".join(ssl.DER_cert_to_PEM_cert(cert) for cert in certificates)
        )
        env["PIP_CERT"] = str(certificate_file)
    env["NODE_USE_SYSTEM_CA"] = "1"
    return env


def fingerprint(paths):
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run(command, env):
    subprocess.run([str(part) for part in command], cwd=ROOT, env=env, check=True)


def open_when_ready(url):
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            threading.Event().wait(0.2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Install/build without starting a server.",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Start without opening a browser."
    )
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535.")
    if sys.version_info < (3, 11):
        raise RuntimeError("Install Python 3.11 or newer first.")
    env = project_environment()
    os.environ.update(env)
    node = shutil.which("node")
    if not node:
        raise RuntimeError(
            "Install Node.js 22.12 or newer first, then reopen your terminal."
        )
    version = subprocess.check_output([node, "--version"], text=True).strip()
    major, minor = map(int, version.lstrip("v").split(".")[:2])
    if (major, minor) < (22, 12):
        raise RuntimeError("Install Node.js 22.12 or newer first.")
    npm_script = Path(node).parent / "node_modules/npm/bin/npm-cli.js"
    npm = (
        [node, str(npm_script)]
        if npm_script.is_file()
        else [shutil.which("npm") or "npm"]
    )
    python = (
        ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    )
    state_path = DATA / "setup.json"
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}

    def save():
        state_path.write_text(json.dumps(state, indent=2) + "\n")

    if not python.is_file():
        print("Creating the project Python environment...", flush=True)
        venv.create(ROOT / ".venv", with_pip=True)
        state.pop("python", None)
    python_key = fingerprint([ROOT / "pyproject.toml", ROOT / "requirements-lock.txt"])
    if state.get("python") != python_key:
        print("Installing locked Python dependencies...", flush=True)
        run(
            [
                python,
                "-m",
                "pip",
                "install",
                "-r",
                "requirements-lock.txt",
                "-e",
                ".[dev]",
            ],
            env,
        )
        state["python"] = python_key
        save()
    frontend = ROOT / "frontend"
    node_key = fingerprint([frontend / "package.json", frontend / "package-lock.json"])
    if (
        state.get("node") != node_key
        or not (frontend / "node_modules/.package-lock.json").is_file()
    ):
        print("Installing locked dashboard dependencies...", flush=True)
        run([*npm, "--prefix", "frontend", "ci"], env)
        state["node"] = node_key
        save()
    source_files = [
        p
        for directory in (frontend / "src", frontend / "public")
        for p in directory.rglob("*")
        if p.is_file()
    ]
    source_files += [p for p in frontend.iterdir() if p.is_file()]
    build_key = fingerprint(source_files)
    if state.get("build") != build_key or not (frontend / "dist/index.html").is_file():
        print("Building the dashboard...", flush=True)
        run([*npm, "--prefix", "frontend", "run", "build"], env)
        state["build"] = build_key
        save()
    if args.setup_only:
        print("RaceOS setup complete. Run python run.py to start.")
        return 0
    url = f"http://127.0.0.1:{args.port}"
    print(f"RaceOS: {url} (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()
    try:
        return subprocess.call(
            [str(python), "-m", "raceos", "serve", "--port", str(args.port)],
            cwd=ROOT,
            env=env,
        )
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
