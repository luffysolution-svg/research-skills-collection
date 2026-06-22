# Engine commands and local configuration

## One-command dependency check

Cross-platform (Windows, macOS, Linux):

```bash
python scripts/document-tools-doctor.py
```

Use `python3` instead of `python` on systems where that is the Python 3 command.

Machine-readable output:

```bash
python scripts/document-tools-doctor.py --json
```

On Windows, the PowerShell wrapper is also available:

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\document-tools-doctor.ps1" -Json
```

Use `--strict` in Python or `-Strict` in PowerShell to return exit code 1 when any required component is missing. The doctor checks MarkItDown, plugin registration, pip dependencies, OCR variables, FFmpeg, audio packages, MinerU, Token presence, and DOC/PPT fallback paths. It never prints API Key or Token values.

## Temporary workspace

Create a marked per-task workspace:

```bash
python scripts/task-workspace.py create
```

Use it only for disposable renders, upgraded DOCX/PPTX files, audio transcodes, comparison outputs, and test artifacts. Cleanup after success or failure:

```bash
python scripts/task-workspace.py cleanup "/path/returned/by/create"
```

The cleanup command refuses paths outside the system temporary directory, paths without the dedicated prefix, symbolic-link workspaces, and directories without a matching marker. Do not place final Markdown or referenced MinerU assets in this workspace. If MinerU creates an asset directory referenced by Markdown, keep the Markdown and asset directory together as final output.

## MarkItDown

Check:

```powershell
Get-Command markitdown
markitdown --version
```

Convert:

```powershell
markitdown "C:\path\file.pdf" -o "C:\path\file.md"
```

The local executable is expected to come from the isolated pipx environment.

Plain MarkItDown conversion is local and does not require an API key.

## Audio

MarkItDown accepts WAV, MP3, M4A, and MP4. Check dependencies before conversion:

```powershell
Get-Command ffmpeg,ffprobe
ffmpeg -version
python -m pipx runpip markitdown show speechrecognition pydub
```

Convert:

```powershell
markitdown "C:\path\speech.mp3" -o "C:\path\speech.md"
```

WAV can be read directly. MP3/M4A/MP4 require FFmpeg decoding. The built-in converter calls the Google SpeechRecognition service, so transcription requires internet access, may be rate-limited, and may misrecognize names or specialist terms. Verify the transcript against a sample of the audio.

If FFmpeg is missing on Windows, ask before installing:

```powershell
winget install --id Gyan.FFmpeg.Essentials --exact --accept-package-agreements --accept-source-agreements
```

On macOS use `brew install ffmpeg`; on Debian/Ubuntu use `sudo apt-get install ffmpeg`. Request permission before installing.

## Legacy Word and PowerPoint

MarkItDown and its OCR plugin target DOCX/PPTX, not binary `.doc`/`.ppt`. Prefer MinerU precision, which accepts the legacy formats directly:

```powershell
mineru-open-api extract "C:\path\legacy.doc" -o "C:\output" -f md
mineru-open-api extract "C:\path\legacy.ppt" -o "C:\output" -f md
```

MinerU precision requires a configured Token.

If MarkItDown output is specifically required, use LibreOffice headless conversion:

```powershell
soffice --headless --convert-to docx --outdir "C:\output" "C:\path\legacy.doc"
soffice --headless --convert-to pptx --outdir "C:\output" "C:\path\legacy.ppt"
```

If LibreOffice is unavailable but desktop Microsoft Office is installed, manually open the file and use Save As DOCX/PPTX. Unattended Office COM conversion can hang on compatibility, protected-view, add-in, or first-run dialogs; use it only after machine-specific validation.

After format upgrade, run MarkItDown for digital content or MarkItDown OCR if the upgraded file contains scans/images. Pandoc can read DOCX/PPTX but not legacy binary DOC/PPT, so it is not the primary converter here.

## MarkItDown OCR

Check:

```powershell
Get-Command markitdown-ocr
markitdown --list-plugins
```

Convert scanned PDF or documents containing images:

```bash
python scripts/markitdown-ocr-convert.py "/path/scan.pdf" -o "/path/scan.md"
```

The same command supports standalone PNG/JPG/WebP/GIF/BMP/TIFF images. On this Windows machine, the convenience command `markitdown-ocr` remains available, but the Python script is the portable interface for Windows, macOS, and Linux.

The wrapper reads these current-user environment variables:

- `MARKITDOWN_OCR_API_KEY`
- `MARKITDOWN_OCR_BASE_URL`
- `MARKITDOWN_OCR_MODEL`

Check only whether the key exists; never print its value.

On Windows, inspect both the current process and current-user environment without revealing secrets:

```powershell
$names='MARKITDOWN_OCR_API_KEY','MARKITDOWN_OCR_BASE_URL','MARKITDOWN_OCR_MODEL'
foreach($name in $names) {
  $value=[Environment]::GetEnvironmentVariable($name,'Process')
  if(-not $value){$value=[Environment]::GetEnvironmentVariable($name,'User')}
  Write-Output "$name configured=$([bool]$value)"
}
```

All three values are required. If any are absent:

1. List only the missing variable names.
2. Explain that OCR needs an OpenAI-compatible vision API provider.
3. If a provider URL is already known, direct the user to that provider's dashboard or key-management page.
4. For this machine, the configured provider is the third-party relay at `https://api.ikuncode.cc/`; do not call it an official OpenAI endpoint.
5. If no provider is known, ask which provider the user wants instead of inventing a signup URL.
6. After the user supplies credentials, save them securely as user environment variables and run a minimal image OCR test.

For a standalone image, create an OpenAI-compatible client from those environment variables and call `markitdown_ocr._ocr_service.LLMVisionOCRService.extract_text()` inside the MarkItDown pipx Python environment.

## MinerU

Check:

```powershell
Get-Command mineru-open-api
mineru-open-api version
```

Quick extraction without a token, only for files below 10 MB and 20 pages:

```powershell
mineru-open-api flash-extract "C:\path\file.pdf" -o "C:\path\output"
mineru-open-api flash-extract "C:\path\scan.pdf" -o "C:\path\output" --ocr
```

Precision extraction:

```powershell
mineru-open-api extract "C:\path\file.pdf" -o "C:\path\output" -f md --model vlm --ocr
```

Flash mode exposes `--ocr`, `--table`, and `--formula`, but may replace complex assets with placeholders. Use `extract` when tables, formulas, or layout must be retained reliably, and for batch processing, files beyond flash limits, or HTML/LaTeX/DOCX/JSON output. It requires a MinerU token configured with `mineru-open-api auth` or `MINERU_TOKEN`.

Before precision extraction, detect authentication without printing the Token:

```powershell
$token=[Environment]::GetEnvironmentVariable('MINERU_TOKEN','Process')
if(-not $token){$token=[Environment]::GetEnvironmentVariable('MINERU_TOKEN','User')}
if($token){
  Write-Output 'MINERU_TOKEN configured=True'
} else {
  mineru-open-api auth --show
}
```

If no Token is configured:

1. Explain that `flash-extract` remains available without login for files within its limits.
2. For precision `extract`, direct the user to the official MinerU Token page: `https://mineru.net/apiManage/token`.
3. Ask the user to create a Token, then configure it with `mineru-open-api auth` or `MINERU_TOKEN`.
4. Verify with `mineru-open-api auth --verify` before extraction.
5. Never request that the user paste a Token into a command that will be logged when a secure interactive or environment-variable option is available.

If the CLI is absent, do not silently substitute another engine when the user explicitly requested MinerU. Ask before installing:

```powershell
npm install -g mineru-open-api
```

## Verification snippets

Use Python to avoid PowerShell 5 UTF-8 display confusion:

```python
from pathlib import Path

text = Path(output_path).read_text(encoding="utf-8")
assert text.strip()
assert "\ufffd" not in text
```

For PDFs, use PyMuPDF or an available PDF renderer to inspect representative pages. Compare the rendered source with the Markdown text, especially tables, formulas, columns, headers, and footers.
