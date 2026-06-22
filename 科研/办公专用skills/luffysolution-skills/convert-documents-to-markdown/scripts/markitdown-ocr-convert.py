#!/usr/bin/env python3
"""Cross-platform MarkItDown OCR entry point."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
from pathlib import Path


def refresh_windows_path() -> None:
    if platform.system() != "Windows":
        return
    try:
        import winreg
    except ImportError:
        return

    paths = [os.environ.get("PATH", "")]
    locations = (
        (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
        (winreg.HKEY_CURRENT_USER, r"Environment"),
    )
    for hive, key_name in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
                if value:
                    paths.append(os.path.expandvars(str(value)))
        except OSError:
            continue
    os.environ["PATH"] = os.pathsep.join(filter(None, paths))


refresh_windows_path()


def get_config(name: str) -> str | None:
    value = os.environ.get(name)
    if value or platform.system() != "Windows":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return str(value) if value else None
    except OSError:
        return None


def load_config() -> tuple[str, str, str]:
    names = (
        "MARKITDOWN_OCR_API_KEY",
        "MARKITDOWN_OCR_BASE_URL",
        "MARKITDOWN_OCR_MODEL",
    )
    values = {name: get_config(name) for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("Missing configuration: " + ", ".join(missing))
    return values[names[0]], values[names[1]], values[names[2]]  # type: ignore[return-value]


def ensure_markitdown_runtime() -> None:
    try:
        import markitdown  # noqa: F401
        import markitdown_ocr  # noqa: F401
        import openai  # noqa: F401

        return
    except ImportError:
        pass

    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pipx",
            "environment",
            "--value",
            "PIPX_LOCAL_VENVS",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(
            "MarkItDown OCR packages are unavailable in this Python environment, "
            "and the pipx environment could not be located."
        )

    venv_root = Path(process.stdout.decode("utf-8", errors="replace").strip())
    python_name = "python.exe" if platform.system() == "Windows" else "python"
    python_path = venv_root / "markitdown" / (
        Path("Scripts") / python_name
        if platform.system() == "Windows"
        else Path("bin") / python_name
    )
    if not python_path.is_file() or python_path.resolve() == Path(sys.executable).resolve():
        raise RuntimeError(
            "The MarkItDown pipx Python interpreter was not found. "
            "Install markitdown-ocr and openai in the MarkItDown environment."
        )
    process = subprocess.run(
        [str(python_path), str(Path(__file__).resolve()), *sys.argv[1:]],
        check=False,
    )
    raise SystemExit(process.returncode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?")
    parser.add_argument("-o", "--output")
    parser.add_argument("--prompt")
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args()

    try:
        api_key, base_url, model = load_config()
    except RuntimeError as exc:
        parser.error(str(exc))

    if args.check_config:
        print("OCR configuration is complete; secret values are hidden.")
        return 0
    if not args.input:
        parser.error("input is required unless --check-config is used")

    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        parser.error(f"input file does not exist: {source}")
    output = (
        Path(args.output).expanduser().resolve()
        if args.output
        else source.with_suffix(".md")
    )
    if output.exists():
        parser.error(f"output already exists: {output}")

    try:
        ensure_markitdown_runtime()
    except RuntimeError as exc:
        parser.error(str(exc))

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=180)
    if source.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
    }:
        from markitdown_ocr._ocr_service import LLMVisionOCRService

        service = LLMVisionOCRService(
            client=client,
            model=model,
            default_prompt=args.prompt,
        )
        with source.open("rb") as stream:
            result = service.extract_text(stream)
        if result.error:
            raise RuntimeError(f"OCR request failed: {result.error}")
        text = result.text
    else:
        from markitdown import MarkItDown

        converter = MarkItDown(
            enable_plugins=True,
            llm_client=client,
            llm_model=model,
            llm_prompt=args.prompt,
        )
        text = converter.convert(source).text_content

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8", newline="\n")
    print("OCR conversion completed successfully.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
