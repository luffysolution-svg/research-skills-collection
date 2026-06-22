#!/usr/bin/env python3
"""Cross-platform dependency doctor for document conversion tools."""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Result:
    component: str
    status: str
    details: str


def windows_registry_environment() -> dict[str, str]:
    if platform.system() != "Windows":
        return {}
    try:
        import winreg
    except ImportError:
        return {}

    values: dict[str, str] = {}
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    )
    for hive, key_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if isinstance(value, str):
                        values[name.upper()] = os.path.expandvars(value)
                    index += 1
        except OSError:
            continue
    return values


REGISTRY_ENV = windows_registry_environment()


def refresh_windows_path() -> None:
    if platform.system() != "Windows":
        return
    path_parts = [os.environ.get("PATH", "")]
    for key in ("PATH",):
        if REGISTRY_ENV.get(key):
            path_parts.append(REGISTRY_ENV[key])
    os.environ["PATH"] = os.pathsep.join(filter(None, path_parts))


refresh_windows_path()


def decode_output(data: bytes) -> str:
    encodings = ["utf-8", locale.getpreferredencoding(False), "gb18030"]
    for encoding in dict.fromkeys(filter(None, encodings)):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run(command: list[str], timeout: int = 30) -> tuple[int, str]:
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return process.returncode, decode_output(process.stdout).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f"{type(exc).__name__}: {exc}"


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def configured(name: str) -> bool:
    return bool(os.environ.get(name) or REGISTRY_ENV.get(name.upper()))


def command_result(name: str) -> tuple[str | None, str]:
    path = shutil.which(name)
    return path, path or "not found on PATH"


def detect_office() -> bool:
    system = platform.system()
    if system == "Windows":
        try:
            import winreg

            keys = (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\WINWORD.EXE",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\POWERPNT.EXE",
            )
            for key_name in keys:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_name):
                    pass
            return True
        except OSError:
            return False
    if system == "Darwin":
        return Path("/Applications/Microsoft Word.app").exists() and Path(
            "/Applications/Microsoft PowerPoint.app"
        ).exists()
    return False


def inspect() -> list[Result]:
    results: list[Result] = []

    markitdown, detail = command_result("markitdown")
    if markitdown:
        code, output = run([markitdown, "--version"])
        results.append(
            Result(
                "MarkItDown CLI",
                "OK" if code == 0 else "WARN",
                f"{first_line(output)}; {markitdown}",
            )
        )
        code, output = run([markitdown, "--list-plugins"])
        plugin_ok = code == 0 and any(
            line.strip().startswith("* ocr") for line in output.splitlines()
        )
        results.append(
            Result(
                "MarkItDown OCR plugin",
                "OK" if plugin_ok else "MISSING",
                "Plugin ocr is registered"
                if plugin_ok
                else "Install markitdown-ocr into the MarkItDown environment",
            )
        )
    else:
        results.append(Result("MarkItDown CLI", "MISSING", detail))
        results.append(
            Result(
                "MarkItDown OCR plugin",
                "MISSING",
                "Cannot inspect plugins without MarkItDown",
            )
        )

    code, _ = run([sys.executable, "-m", "pipx", "--version"])
    if code == 0:
        code, output = run(
            [sys.executable, "-m", "pipx", "runpip", "markitdown", "check"]
        )
        clean = code == 0 and "compatible" in output.lower()
        results.append(
            Result(
                "MarkItDown Python dependencies",
                "OK" if clean else "WARN",
                "pip check reports compatible packages"
                if clean
                else "Could not confirm a clean pip dependency state",
            )
        )
    elif markitdown:
        results.append(
            Result(
                "pipx",
                "WARN",
                "MarkItDown exists, but python -m pipx is unavailable",
            )
        )

    ocr_names = (
        "MARKITDOWN_OCR_API_KEY",
        "MARKITDOWN_OCR_BASE_URL",
        "MARKITDOWN_OCR_MODEL",
    )
    missing_ocr = [name for name in ocr_names if not configured(name)]
    results.append(
        Result(
            "OCR model configuration",
            "MISSING" if missing_ocr else "OK",
            "Missing: " + ", ".join(missing_ocr)
            if missing_ocr
            else "API key, base URL, and model are configured; values are hidden",
        )
    )

    for name in ("ffmpeg", "ffprobe"):
        path, detail = command_result(name)
        if path:
            code, output = run([path, "-version"])
            results.append(
                Result(
                    name,
                    "OK" if code == 0 else "WARN",
                    f"{first_line(output)}; {path}",
                )
            )
        else:
            results.append(
                Result(name, "MISSING", f"{detail}; required for MP3/M4A/MP4 decoding")
            )

    if markitdown:
        code, output = run(
            [
                sys.executable,
                "-m",
                "pipx",
                "runpip",
                "markitdown",
                "show",
                "speechrecognition",
                "pydub",
            ]
        )
        normalized = output.lower()
        for package in ("speechrecognition", "pydub"):
            installed = code == 0 and f"name: {package}" in normalized
            results.append(
                Result(
                    f"Audio package: {package}",
                    "OK" if installed else "MISSING",
                    "Installed in the MarkItDown environment"
                    if installed
                    else "Install MarkItDown audio/all optional dependencies",
                )
            )

    mineru, detail = command_result("mineru-open-api")
    if mineru:
        code, output = run([mineru, "version"])
        results.append(
            Result(
                "MinerU CLI",
                "OK" if code == 0 else "WARN",
                f"{first_line(output)}; {mineru}",
            )
        )
        if configured("MINERU_TOKEN"):
            token_stored = True
            token_detail = "Configured through an environment variable; value is hidden"
        else:
            code, output = run([mineru, "auth", "--show"])
            token_stored = code == 0 and "token source:" in output.lower()
            token_detail = (
                "Configured in MinerU CLI storage; value is hidden"
                if token_stored
                else (
                    "Flash mode remains available; precision mode needs "
                    "https://mineru.net/apiManage/token"
                )
            )
        results.append(
            Result(
                "MinerU precision Token",
                "OK" if token_stored else "MISSING",
                token_detail,
            )
        )
    else:
        results.append(Result("MinerU CLI", "MISSING", detail))
        results.append(
            Result(
                "MinerU precision Token",
                "INFO",
                "Not checked because MinerU CLI is unavailable",
            )
        )

    office_converter = shutil.which("soffice") or shutil.which("libreoffice")
    results.append(
        Result(
            "LibreOffice legacy conversion",
            "OK" if office_converter else "INFO",
            office_converter
            or "Not installed; MinerU precision can parse DOC/PPT directly",
        )
    )
    office_installed = detect_office()
    results.append(
        Result(
            "Microsoft Office manual fallback",
            "OK" if office_installed else "INFO",
            "Word and PowerPoint are installed"
            if office_installed
            else "Word and/or PowerPoint was not detected",
        )
    )
    return results


def print_table(results: list[Result]) -> None:
    headers = ("Component", "Status", "Details")
    rows = [(item.component, item.status, item.details) for item in results]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(3)
    ]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(3)))
    print("  ".join("-" * widths[i] for i in range(3)))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(3)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    results = inspect()
    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        print_table(results)
    return 1 if args.strict and any(item.status == "MISSING" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
