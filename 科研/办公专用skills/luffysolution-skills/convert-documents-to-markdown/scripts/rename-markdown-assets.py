import argparse
import base64
import csv
import hashlib
import html
import json
import math
import mimetypes
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.parse import unquote
from urllib import request as urllib_request


@dataclass(frozen=True)
class Reference:
    markdown_path: Path
    syntax: str
    start: int
    end: int
    raw_destination: str
    decoded_destination: str
    asset_path: Path
    encoding_style: str


@dataclass
class AssetRecord:
    path: Path
    sha256: str
    references: list[Reference]
    evidence: list[dict[str, object]]
    proposed_name: str = ""
    reason: str = ""


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".svg",
}

VISION_ENV = (
    "MARKITDOWN_OCR_API_KEY",
    "MARKITDOWN_OCR_BASE_URL",
    "MARKITDOWN_OCR_MODEL",
)
PROMPT_VERSION = "semantic-asset-name-v1"
DEFAULT_VISION_BASE_URL = "https://api.openai.com/v1"
DEFAULT_VISION_MODEL = "gpt-4.1-mini"
VISION_CONFIDENCE_THRESHOLD = 0.65
CACHE_FILENAME = ".asset-name-cache.json"


WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _windows_user_env(name: str) -> str:
    if os.name != "nt":
        return ""
    try:
        import winreg
    except ImportError:
        return ""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Environment",
        ) as key:
            value, _value_type = winreg.QueryValueEx(key, name)
    except OSError:
        return ""
    return str(value)


def _env_value(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    return _windows_user_env(name)


def classify_base_url(base_url: str) -> str:
    normalized = base_url.casefold()
    if "api.ikuncode.cc" in normalized:
        return "third-party OpenAI-compatible relay"
    if "api.openai.com" in normalized:
        return "official OpenAI API"
    if normalized:
        return "OpenAI-compatible endpoint"
    return "not configured"


def load_vision_config() -> dict[str, object]:
    api_key = _env_value("MARKITDOWN_OCR_API_KEY")
    base_url = _env_value("MARKITDOWN_OCR_BASE_URL")
    model = _env_value("MARKITDOWN_OCR_MODEL")
    base_url = base_url.rstrip("/") or DEFAULT_VISION_BASE_URL
    model = model or DEFAULT_VISION_MODEL
    return {
        "api_key": api_key,
        "base_url": base_url,
        "base_url_classification": classify_base_url(base_url),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "configured": bool(api_key),
    }


def vision_cache_key(
    sha256: str,
    model: str,
    prompt_version: str,
) -> str:
    return "sha256={};model={};prompt={}".format(
        sha256,
        model,
        prompt_version,
    )


def _load_vision_cache(output_dir: Path) -> dict[str, object]:
    cache_path = output_dir / CACHE_FILENAME
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema": 1, "entries": {}}
    if not isinstance(cache, dict):
        return {"schema": 1, "entries": {}}
    entries = cache.get("entries")
    if not isinstance(entries, dict):
        cache["entries"] = {}
    cache["schema"] = 1
    return cache


def _write_vision_cache(output_dir: Path, cache: dict[str, object]) -> None:
    sanitized = {
        "schema": 1,
        "entries": cache.get("entries", {}),
    }
    cache_path = output_dir / CACHE_FILENAME
    with cache_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(
                sanitized,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        stream.write("\n")


def _image_data_url(path: Path) -> str:
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:{};base64,{}".format(media_type, encoded)


def _json_response_content(response: dict[str, object]) -> object:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("vision response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("vision response choice is not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("vision response missing message")
    if "parsed" in message:
        return message["parsed"]
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("vision response content is not text")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("vision response content is not JSON") from exc


def _validate_vision_result(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("vision result is not an object")
    description = value.get("description")
    keywords = value.get("keywords", [])
    confidence = value.get("confidence")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("vision result missing description")
    if not isinstance(keywords, list):
        raise ValueError("vision result keywords must be a list")
    cleaned_keywords = [
        str(keyword).strip()
        for keyword in keywords
        if str(keyword).strip()
    ]
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("vision result confidence must be numeric")
    return {
        "description": re.sub(r"\s+", " ", description).strip(),
        "keywords": cleaned_keywords,
        "confidence": float(confidence),
    }


def analyze_image_with_vision(
    path: Path,
    context: dict[str, object],
    config: dict[str, object],
) -> dict[str, object]:
    api_key = str(config.get("api_key") or "")
    if not api_key:
        raise RuntimeError("MARKITDOWN_OCR_API_KEY is not configured")
    base_url = str(config.get("base_url") or DEFAULT_VISION_BASE_URL).rstrip("/")
    model = str(config.get("model") or DEFAULT_VISION_MODEL)
    endpoint = "{}/chat/completions".format(base_url)
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Describe the supplied Markdown image for a stable, "
                    "semantic file name. Return only JSON with description, "
                    "keywords, and confidence."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "prompt_version": PROMPT_VERSION,
                                "context": context,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _image_data_url(path),
                        },
                    },
                ],
            },
        ],
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = urllib_request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": "Bearer {}".format(api_key),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(http_request, timeout=60) as response:
        raw_response = response.read().decode("utf-8")
    parsed_response = json.loads(raw_response)
    return _validate_vision_result(_json_response_content(parsed_response))


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower())
    return re.sub(r"-+", "-", slug).strip("-")


def safe_filename(
    stem: str, suffix: str, hash8: str, limit: int = 120
) -> str:
    slug = slugify(stem) or "asset"
    if slug.casefold() in WINDOWS_RESERVED:
        slug = "asset"
    tail = f"-{hash8}{suffix.lower()}"
    available = max(1, limit - len(tail))
    slug = slug[:available].rstrip("-") or "asset"
    return f"{slug}{tail}"


def _safe_filename_with_hashes(
    stem: str,
    suffix: str,
    hashes: list[str],
    limit: int = 120,
) -> str:
    slug = slugify(stem) or "asset"
    if slug.casefold() in WINDOWS_RESERVED:
        slug = "asset"
    tail = f"-{'-'.join(hashes)}{suffix.lower()}"
    available = max(1, limit - len(tail))
    slug = slug[:available].rstrip("-") or "asset"
    return f"{slug}{tail}"


def _overlaps(ranges: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < range_end and end > range_start
               for range_start, range_end in ranges)


def _is_escaped(text: str, position: int) -> bool:
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


FENCE_LINE_PATTERN = re.compile(
    r"^(?P<quotes>(?: {0,3}>[ \t]?)*)(?P<indent> {0,3})"
    r"(?P<marker>`{3,}|~{3,})(?P<rest>.*)$"
)


def _line_bounds(text: str, start: int) -> tuple[int, int]:
    line_end = text.find("\n", start)
    if line_end == -1:
        return len(text), len(text)
    content_end = (
        line_end - 1
        if line_end > start and text[line_end - 1] == "\r"
        else line_end
    )
    return content_end, line_end + 1


def _fence_line(
    text: str, line_start: int
) -> Optional[tuple[int, str, int, str, int, int]]:
    content_end, next_line = _line_bounds(text, line_start)
    match = FENCE_LINE_PATTERN.match(text[line_start:content_end])
    if match is None:
        return None
    marker = match.group("marker")
    rest = match.group("rest")
    if marker[0] == "`" and "`" in rest:
        return None
    return (
        match.group("quotes").count(">"),
        marker[0],
        len(marker),
        rest,
        content_end,
        next_line,
    )


def _fence_end(
    text: str,
    next_line: int,
    quote_depth: int,
    marker_character: str,
    marker_length: int,
) -> tuple[int, int]:
    line_start = next_line
    while line_start < len(text):
        parsed = _fence_line(text, line_start)
        if parsed is not None:
            depth, character, length, rest, content_end, after_line = parsed
            if (
                depth == quote_depth
                and character == marker_character
                and length >= marker_length
                and not rest.strip()
            ):
                return content_end, after_line
        _content_end, line_start = _line_bounds(text, line_start)
    return len(text), len(text)


def _inline_code_end(
    text: str, start: int, delimiter: str
) -> Optional[int]:
    position = start + len(delimiter)
    while position < len(text):
        line_start = position == 0 or text[position - 1] == "\n"
        if line_start and _fence_line(text, position) is not None:
            return None
        if text.startswith(delimiter, position):
            if (
                not _is_escaped(text, position)
                and (position == 0 or text[position - 1] != "`")
                and (
                    position + len(delimiter) == len(text)
                    or text[position + len(delimiter)] != "`"
                )
            ):
                return position + len(delimiter)
            position += len(delimiter)
            continue
        position += 1
    return None


def protected_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    position = 0
    while position < len(text):
        line_start = position == 0 or text[position - 1] == "\n"
        if line_start:
            fence = _fence_line(text, position)
            if fence is not None:
                depth, character, length, _rest, _line_end, next_line = fence
                end, after_fence = _fence_end(
                    text, next_line, depth, character, length
                )
                ranges.append((position, end))
                position = after_fence
                continue

        if text.startswith("<!--", position):
            comment_end = text.find("-->", position + 4)
            end = comment_end + 3 if comment_end != -1 else len(text)
            ranges.append((position, end))
            position = end
            continue

        if text[position] == "`" and not _is_escaped(text, position):
            delimiter_end = position + 1
            while delimiter_end < len(text) and text[delimiter_end] == "`":
                delimiter_end += 1
            delimiter = text[position:delimiter_end]
            end = _inline_code_end(text, position, delimiter)
            if end is not None:
                ranges.append((position, end))
                position = end
                continue
            position = delimiter_end
            continue

        position += 1
    return ranges


def _without_url_suffix(destination: str) -> str:
    for position, character in enumerate(destination):
        if character in "?#" and not _is_escaped(destination, position):
            return destination[:position]
    return destination


def destination_to_asset(
    markdown_path: Path, root: Path, raw_destination: str
) -> Optional[tuple[str, Path]]:
    entity_destination = html.unescape(raw_destination)
    scheme_destination = unquote(entity_destination)
    scheme_path = Path(scheme_destination)
    if (
        not scheme_path.is_absolute()
        and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", scheme_destination)
    ):
        return None

    decoded_destination = unquote(_without_url_suffix(entity_destination))
    decoded_destination = re.sub(
        r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~\\ \t])""",
        r"\1",
        decoded_destination,
    )
    if not decoded_destination:
        return None
    destination_path = Path(decoded_destination)

    canonical_root = root.resolve(strict=False)
    if destination_path.is_absolute():
        candidate = destination_path.resolve(strict=False)
    else:
        candidate = (
            markdown_path.resolve(strict=False).parent / destination_path
        ).resolve(strict=False)

    if not candidate.is_relative_to(canonical_root):
        return None
    return decoded_destination, candidate


def _destination_span(
    text: str, opening_parenthesis: int
) -> Optional[tuple[int, int]]:
    position = opening_parenthesis + 1
    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    if position >= len(text):
        return None

    if text[position] == "<":
        start = position + 1
        position = start
        while position < len(text):
            if text[position] in "\r\n":
                return None
            if text[position] == ">" and (
                position == start or text[position - 1] != "\\"
            ):
                end = position
                position += 1
                break
            position += 1
        else:
            return None
    else:
        start = position
        nested_parentheses = 0
        while position < len(text):
            character = text[position]
            if character == "\\":
                position += 2
                continue
            if character == "(":
                nested_parentheses += 1
            elif character == ")":
                if nested_parentheses == 0:
                    break
                nested_parentheses -= 1
            elif character.isspace() and nested_parentheses == 0:
                break
            position += 1
        if position == start:
            return None
        end = position

    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    if position < len(text) and text[position] in "\"'":
        quote = text[position]
        position += 1
        while position < len(text):
            if text[position] == quote and not _is_escaped(text, position):
                position += 1
                break
            position += 1
        else:
            return None
        while position < len(text) and text[position] in " \t\r\n":
            position += 1
    return (start, end) if position < len(text) and text[position] == ")" else None


def _closing_bracket(
    text: str, opening_bracket: int
) -> Optional[int]:
    depth = 1
    position = opening_bracket + 1
    while position < len(text):
        character = text[position]
        if character in "\r\n":
            return None
        if character == "\\":
            position += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return position
        position += 1
    return None


def _reference_label(value: str) -> str:
    value = re.sub(
        r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~\\])""",
        r"\1",
        value,
    )
    return re.sub(r"\s+", " ", value.strip()).casefold()


def scan_markdown(path: Path, root: Path) -> list[Reference]:
    encoded_text = path.read_bytes()
    text = encoded_text.decode("utf-8")
    protected = protected_ranges(text)
    byte_offsets = [0]
    for character in text:
        byte_offsets.append(
            byte_offsets[-1] + len(character.encode("utf-8"))
        )

    found: list[tuple[int, Reference]] = []

    def add_reference(
        syntax: str, start: int, end: int, raw_destination: str
    ) -> None:
        asset = destination_to_asset(path, root, raw_destination)
        if asset is None:
            return
        decoded_destination, asset_path = asset
        encoding_style = (
            "percent"
            if re.search(r"%[0-9A-Fa-f]{2}", raw_destination)
            else "raw"
        )
        found.append(
            (
                start,
                Reference(
                    markdown_path=path,
                    syntax=syntax,
                    start=byte_offsets[start],
                    end=byte_offsets[end],
                    raw_destination=raw_destination,
                    decoded_destination=decoded_destination,
                    asset_path=asset_path,
                    encoding_style=encoding_style,
                ),
            )
        )

    used_labels: set[str] = set()
    position = 0
    while position < len(text):
        marker = text.find("![", position)
        if marker == -1:
            break
        if (
            _is_escaped(text, marker)
            or _overlaps(protected, marker, marker + 2)
        ):
            position = marker + 2
            continue
        alt_end = _closing_bracket(text, marker + 1)
        if alt_end is None:
            position = marker + 2
            continue
        alt = text[marker + 2 : alt_end]
        following = alt_end + 1
        if following < len(text) and text[following] == "(":
            span = _destination_span(text, following)
            if span is not None and not _overlaps(protected, *span):
                start, end = span
                add_reference(
                    "markdown-inline", start, end, text[start:end]
                )
            position = following + 1
            continue
        if following < len(text) and text[following] == "[":
            label_end = _closing_bracket(text, following)
            if label_end is not None:
                label = text[following + 1 : label_end] or alt
                used_labels.add(_reference_label(label))
                position = label_end + 1
                continue
        used_labels.add(_reference_label(alt))
        position = following

    defined_labels: set[str] = set()
    definition_start_pattern = re.compile(r"(?m)^[ \t]{0,3}\[")
    for match in definition_start_pattern.finditer(text):
        label_end = _closing_bracket(text, match.end() - 1)
        if label_end is None:
            continue
        position = label_end + 1
        if position >= len(text) or text[position] != ":":
            continue
        position += 1
        while position < len(text) and text[position] in " \t":
            position += 1
        if position < len(text) and text[position] in "\r\n":
            if text.startswith("\r\n", position):
                position += 2
            else:
                position += 1
            indentation_start = position
            while position < len(text) and text[position] == " ":
                position += 1
            if not 1 <= position - indentation_start <= 3:
                continue
        if position >= len(text) or text[position] in "\r\n":
            continue
        if text[position] == "<":
            start = position + 1
            end = start
            while end < len(text) and text[end] not in "\r\n":
                if text[end] == ">" and not _is_escaped(text, end):
                    break
                end += 1
            if end >= len(text) or text[end] != ">":
                continue
        else:
            start = position
            end = start
            while end < len(text) and not text[end].isspace():
                end += 1
        if start == end or _overlaps(protected, match.start(), end):
            continue
        label = _reference_label(text[match.end() : label_end])
        if label in defined_labels:
            continue
        defined_labels.add(label)
        if label not in used_labels:
            continue
        add_reference("markdown-reference", start, end, text[start:end])

    image_tag_pattern = re.compile(
        r"""<img\b(?:[^"'<>]|"[^"]*"|'[^']*')*>""",
        re.IGNORECASE,
    )
    source_pattern = re.compile(
        r"""(?<!\S)src\s*=\s*(?:
            "(?P<double>[^"]*)"
            |'(?P<single>[^']*)'
            |(?P<bare>[^\s>]+)
        )""",
        re.IGNORECASE | re.VERBOSE,
    )
    for tag in image_tag_pattern.finditer(text):
        if _overlaps(protected, tag.start(), tag.end()):
            continue
        source = source_pattern.search(tag.group())
        if source is None:
            continue
        group = next(
            name
            for name in ("double", "single", "bare")
            if source.group(name) is not None
        )
        relative_start, relative_end = source.span(group)
        start = tag.start() + relative_start
        end = tag.start() + relative_end
        add_reference("html-img", start, end, text[start:end])

    return [reference for _, reference in sorted(found, key=lambda item: item[0])]


def iter_markdown_files(root: Path) -> list[Path]:
    canonical_root = root.resolve(strict=False)
    documents: set[Path] = set()
    for path in canonical_root.rglob("*"):
        if path.suffix.casefold() != ".md" or not path.is_file():
            continue
        try:
            canonical_path = path.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if (
            canonical_path.is_relative_to(canonical_root)
            and canonical_path.is_file()
        ):
            documents.add(canonical_path)
    return sorted(documents)


METADATA_PATH_KEYS = (
    "img_path",
    "image_path",
    "asset_path",
    "image",
    "path",
)
METADATA_CAPTION_KEYS = (
    "image_caption",
    "table_caption",
    "chart_caption",
    "caption",
)
METADATA_TYPE_KEYS = ("visual_type", "sub_type", "type")
METADATA_PAGE_KEYS = ("page_idx", "page_index", "page")
MAX_METADATA_INTEGER_DIGITS = 4300
METADATA_RECORD_KEYS = (
    METADATA_PATH_KEYS
    + METADATA_CAPTION_KEYS
    + METADATA_TYPE_KEYS
    + METADATA_PAGE_KEYS
    + ("bbox",)
)


def _metadata_files(root: Path) -> list[Path]:
    canonical_root = root.resolve(strict=False)
    metadata_files: set[Path] = set()
    for path in canonical_root.rglob("*"):
        if path.suffix.casefold() != ".json":
            continue
        if re.fullmatch(
            r"(?:content_list(?:_v2)?|.+_content_list(?:_v2)?)\.json",
            path.name,
            re.IGNORECASE,
        ) is None:
            continue
        try:
            canonical_path = path.resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if (
            not canonical_path.is_relative_to(canonical_root)
            or not canonical_path.is_file()
        ):
            continue
        metadata_files.add(canonical_path)
    return sorted(metadata_files)


def _metadata_records(value, inherited=None):
    inherited = {} if inherited is None else inherited
    if isinstance(value, list):
        for item in value:
            yield from _metadata_records(item, inherited)
        return
    if not isinstance(value, dict):
        return

    own_fields = {
        key: value[key]
        for key in METADATA_RECORD_KEYS
        if key in value
    }
    merged = dict(inherited)
    merged.update(own_fields)
    children = [
        item
        for key, item in value.items()
        if key not in METADATA_RECORD_KEYS
        and isinstance(item, (dict, list))
    ]
    child_records = []
    for child in children:
        child_records.extend(_metadata_records(child, merged))
    if child_records:
        yield from child_records
    elif own_fields and any(key in merged for key in METADATA_PATH_KEYS):
        yield merged


def _safe_json_integer(value: str) -> Union[int, str]:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_METADATA_INTEGER_DIGITS:
        return value
    try:
        return int(value)
    except ValueError:
        return value


def _caption_text(record: dict[str, object]) -> str:
    for key in METADATA_CAPTION_KEYS:
        if key not in record:
            continue
        value = record[key]
        if isinstance(value, str):
            caption = re.sub(r"\s+", " ", value).strip()
            if caption:
                return caption
        if isinstance(value, list):
            parts = [
                re.sub(r"\s+", " ", item).strip()
                for item in value
                if re.sub(r"\s+", " ", item).strip()
            ]
            if parts:
                return " ".join(parts)
    return ""


def _visual_type(record: dict[str, object]) -> str:
    for key in METADATA_TYPE_KEYS:
        value = record.get(key)
        if isinstance(value, str):
            normalized = re.sub(r"\s+", " ", value).strip()
            if normalized:
                return normalized
    return "image"


def _parse_page_index(
    record: dict[str, object],
) -> tuple[bool, Optional[int]]:
    key = next(
        (key for key in METADATA_PAGE_KEYS if key in record),
        None,
    )
    if key is None:
        return True, None
    value = record[key]
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int):
        return (True, value) if value >= 0 else (False, None)
    if isinstance(value, float):
        if math.isfinite(value) and value >= 0 and value.is_integer():
            return True, int(value)
        return False, None
    if isinstance(value, str):
        if (
            len(value) <= MAX_METADATA_INTEGER_DIGITS
            and re.fullmatch(r"\d+", value)
        ):
            try:
                return True, int(value)
            except ValueError:
                pass
    return False, None


def _bbox(
    record: dict[str, object],
) -> Optional[list[Union[int, float]]]:
    value = record.get("bbox")
    if not isinstance(value, list) or not value:
        return None
    normalized = []
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(
            coordinate, (int, float)
        ):
            return None
        try:
            if not math.isfinite(coordinate):
                return None
        except OverflowError:
            return None
        normalized.append(coordinate)
    return normalized


def _valid_metadata_record(record: dict[str, object]) -> bool:
    for key in METADATA_CAPTION_KEYS:
        if key not in record:
            continue
        value = record[key]
        if not isinstance(value, (str, list)):
            return False
        if isinstance(value, list) and not all(
            isinstance(item, str) for item in value
        ):
            return False

    for key in METADATA_TYPE_KEYS:
        if key not in record:
            continue
        value = record[key]
        if (
            not isinstance(value, str)
            or not re.sub(r"\s+", " ", value).strip()
        ):
            return False

    if "bbox" in record and _bbox(record) is None:
        return False
    return True


def _metadata_asset_path(
    record: dict[str, object],
    metadata_path: Path,
    root: Path,
) -> Optional[Path]:
    raw_path = next(
        (
            record[key]
            for key in METADATA_PATH_KEYS
            if isinstance(record.get(key), (str, Path))
            and str(record[key]).strip()
        ),
        None,
    )
    if raw_path is None:
        return None

    raw_text = str(raw_path).strip()
    if not raw_text or "\x00" in raw_text:
        return None
    decoded_path = unquote(
        _without_url_suffix(html.unescape(raw_text))
    ).strip()
    if not decoded_path or "\x00" in decoded_path:
        return None
    try:
        parsed_path = Path(decoded_path)
    except (OSError, ValueError):
        return None
    if (
        not parsed_path.is_absolute()
        and re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", decoded_path)
    ):
        return None

    canonical_root = root.resolve(strict=False)
    try:
        if parsed_path.is_absolute():
            candidates = [parsed_path.resolve(strict=False)]
        else:
            candidates = [
                (metadata_path.parent / parsed_path).resolve(strict=False),
                (canonical_root / parsed_path).resolve(strict=False),
            ]
    except (OSError, RuntimeError, ValueError):
        return None
    contained = [
        candidate
        for candidate in candidates
        if candidate.is_relative_to(canonical_root)
    ]
    if not contained:
        return None
    candidate = next(
        (path for path in contained if path.exists()),
        contained[0],
    )
    if candidate.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS:
        return None
    return candidate


def load_mineru_metadata(
    root: Path,
) -> dict[Path, list[dict[str, object]]]:
    canonical_root = root.resolve(strict=False)
    metadata: dict[Path, list[dict[str, object]]] = {}
    seen: set[tuple[object, ...]] = set()
    for metadata_path in _metadata_files(canonical_root):
        try:
            value = json.loads(
                metadata_path.read_text(encoding="utf-8"),
                parse_int=_safe_json_integer,
            )
            source = metadata_path.stem
            file_evidence = []
            file_seen = set()
            for record in _metadata_records(value):
                page_valid, page_index = _parse_page_index(record)
                if not page_valid or not _valid_metadata_record(record):
                    continue
                asset_path = _metadata_asset_path(
                    record, metadata_path, canonical_root
                )
                if asset_path is None:
                    continue
                evidence = {
                    "path": str(asset_path),
                    "caption": _caption_text(record),
                    "visual_type": _visual_type(record),
                    "page_idx": page_index,
                    "bbox": _bbox(record),
                    "source": source,
                }
                identity = (
                    metadata_path,
                    asset_path,
                    evidence["caption"],
                    evidence["visual_type"],
                    evidence["page_idx"],
                    repr(evidence["bbox"]),
                )
                if identity in seen or identity in file_seen:
                    continue
                file_seen.add(identity)
                file_evidence.append((asset_path, evidence))
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            RecursionError,
        ):
            continue
        seen.update(file_seen)
        for asset_path, evidence in file_evidence:
            metadata.setdefault(asset_path, []).append(evidence)
    return {
        path: metadata[path]
        for path in sorted(metadata)
    }


def build_asset_graph(
    root: Path,
) -> tuple[list[Path], dict[Path, AssetRecord], list[dict[str, str]]]:
    canonical_root = root.resolve(strict=False)
    documents = iter_markdown_files(canonical_root)
    grouped: dict[Path, list[Reference]] = {}
    for document in documents:
        for reference in scan_markdown(document, canonical_root):
            if (
                reference.asset_path.suffix.casefold()
                not in SUPPORTED_IMAGE_EXTENSIONS
            ):
                continue
            grouped.setdefault(reference.asset_path, []).append(reference)

    metadata = load_mineru_metadata(canonical_root)
    assets: dict[Path, AssetRecord] = {}
    warnings: list[dict[str, str]] = []
    referenced_directories: set[Path] = set()
    for asset_path in sorted(grouped):
        if not asset_path.is_file():
            warnings.append(
                {
                    "code": "missing-asset",
                    "path": str(asset_path),
                }
            )
            continue
        referenced_directories.add(asset_path.parent)
        assets[asset_path] = AssetRecord(
            path=asset_path,
            sha256=sha256_file(asset_path),
            references=grouped[asset_path],
            evidence=list(metadata.get(asset_path, [])),
        )

    referenced_paths = set(grouped)
    unreferenced_paths: set[Path] = set()
    scan_directories: list[Path] = []
    for directory in sorted(
        referenced_directories, key=lambda path: (len(path.parts), path)
    ):
        if not any(
            directory.is_relative_to(parent)
            for parent in scan_directories
        ):
            scan_directories.append(directory)

    for directory in scan_directories:
        if not directory.is_dir():
            continue
        for candidate in directory.rglob("*"):
            if (
                not candidate.is_file()
                or candidate.suffix.casefold()
                not in SUPPORTED_IMAGE_EXTENSIONS
            ):
                continue
            canonical_candidate = candidate.resolve(strict=False)
            if (
                canonical_candidate.is_relative_to(canonical_root)
                and canonical_candidate not in referenced_paths
            ):
                unreferenced_paths.add(canonical_candidate)
    warnings.extend(
        {
            "code": "unreferenced-asset",
            "path": str(path),
        }
        for path in sorted(unreferenced_paths)
    )
    return documents, assets, warnings


CAPTION_LABEL_PATTERN = re.compile(
    r"^\s*(?P<label>"
    r"figure|fig\.?|图|table|表|chart"
    r")\s*(?P<number>\d+)?\s*[\.:：、-]?\s*",
    re.IGNORECASE,
)


def _clean_markdown_text(value: str) -> str:
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[`*_~]+", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _reference_character_offset(encoded: bytes, byte_offset: int) -> int:
    bounded_offset = min(max(byte_offset, 0), len(encoded))
    return len(encoded[:bounded_offset].decode("utf-8"))


def _reference_alt_text(
    text: str, character_offset: int, syntax: str
) -> str:
    line_start = text.rfind("\n", 0, character_offset) + 1
    line_end = text.find("\n", character_offset)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    relative_offset = character_offset - line_start
    prefix = line[:relative_offset]

    markdown_match = re.search(
        r"!\[(?P<alt>(?:\\.|[^\]])*)\]\(\s*<?[^<>()]*$",
        prefix,
    )
    if markdown_match is not None:
        return _clean_markdown_text(
            re.sub(r"\\(.)", r"\1", markdown_match.group("alt"))
        )

    if syntax == "markdown-reference":
        definition = re.match(
            r"[ \t]*\[([^\]]+)\][ \t]*:[ \t]*<?",
            line,
        )
        if definition is not None:
            label = _reference_label(definition.group(1))
            for match in re.finditer(
                r"!\[(?P<alt>(?:\\.|[^\]])*)\]"
                r"(?:\[(?P<label>(?:\\.|[^\]])*)\])?",
                text,
            ):
                alt = re.sub(r"\\(.)", r"\1", match.group("alt"))
                raw_label = match.group("label")
                candidate_label = alt if raw_label in (None, "") else raw_label
                if _reference_label(candidate_label) == label:
                    return _clean_markdown_text(alt)

    tag_start = line.rfind("<", 0, relative_offset)
    tag_end = line.find(">", relative_offset)
    if tag_start != -1 and tag_end != -1:
        tag = line[tag_start : tag_end + 1]
        if re.match(r"<img\b", tag, re.IGNORECASE):
            alt_match = re.search(
                r"""(?<!\S)alt\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""",
                tag,
                re.IGNORECASE,
            )
            if alt_match is not None:
                return _clean_markdown_text(
                    next(
                        value
                        for value in alt_match.groups()
                        if value is not None
                    )
                )
    return ""


def _paragraph_blocks(text: str) -> list[tuple[int, int, str]]:
    blocks = []
    for match in re.finditer(r"(?ms)(?:^|\n[ \t]*\n)([^\n].*?)(?=\n[ \t]*\n|\Z)", text):
        raw = match.group(1).strip()
        cleaned = _clean_markdown_text(raw)
        if cleaned:
            blocks.append((match.start(1), match.end(1), cleaned))
    return blocks


def markdown_context(reference: Reference) -> dict[str, str]:
    encoded = reference.markdown_path.read_bytes()
    text = encoded.decode("utf-8")
    character_offset = _reference_character_offset(encoded, reference.start)
    alt_text = _reference_alt_text(
        text, character_offset, reference.syntax
    )

    captions = []
    for match in re.finditer(r"(?m)^[ \t]*(?:Figure|Fig\.?|图|Table|表|Chart)\s*\d*"
                             r"\s*[\.:：、-]?\s*\S.*$", text, re.IGNORECASE):
        distance = min(
            abs(match.start() - character_offset),
            abs(match.end() - character_offset),
        )
        if distance <= 500:
            captions.append((distance, match.start(), _clean_markdown_text(match.group())))
    nearby_caption = min(captions)[2] if captions else ""

    headings = [
        (match.start(), _clean_markdown_text(match.group(1)))
        for match in re.finditer(
            r"(?m)^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$",
            text[:character_offset],
        )
        if _clean_markdown_text(match.group(1))
    ]
    nearest_heading = headings[-1][1] if headings else ""

    before = []
    after = []
    for start, end, paragraph in _paragraph_blocks(text):
        if (
            paragraph.startswith("#")
            or CAPTION_LABEL_PATTERN.match(paragraph)
            or start <= character_offset <= end
            or re.search(r"!\[[^\]]*\]\([^)]*\)|<img\b", text[start:end],
                         re.IGNORECASE)
        ):
            continue
        if end < character_offset:
            before.append((end, paragraph))
        elif start > character_offset:
            after.append((start, paragraph))
    if before:
        nearby_paragraph = before[-1][1]
    elif after:
        nearby_paragraph = after[0][1]
    else:
        nearby_paragraph = ""

    return {
        "alt_text": alt_text,
        "nearby_caption": nearby_caption,
        "nearest_heading": nearest_heading,
        "nearby_paragraph": nearby_paragraph,
    }


def _normalized_visual_type(value: str, semantic_text: str) -> str:
    label = CAPTION_LABEL_PATTERN.match(semantic_text)
    if label is not None:
        label_text = label.group("label").casefold().rstrip(".")
        if label_text in {"table", "表"}:
            return "table"
        if label_text == "chart":
            return "chart"
        return "figure"
    normalized = value.casefold()
    if "table" in normalized or normalized == "表":
        return "table"
    if "chart" in normalized or "plot" in normalized or "graph" in normalized:
        return "chart"
    return "figure"


def choose_evidence(
    record: AssetRecord,
    metadata: dict[Path, list[dict[str, object]]],
) -> tuple[str, str, str]:
    evidence = list(record.evidence)
    if not evidence:
        evidence = list(metadata.get(record.path, []))
    for item in evidence:
        caption = item.get("caption", "")
        if isinstance(caption, str) and caption.strip():
            caption = re.sub(r"\s+", " ", caption).strip()
            visual_type = _normalized_visual_type(
                str(item.get("visual_type", "image")), caption
            )
            if item.get("source") == "vision":
                return visual_type, caption, "vision"
            return visual_type, caption, "mineru-caption"

    contexts = [
        markdown_context(reference)
        for reference in sorted(
            record.references,
            key=lambda item: (
                item.markdown_path.as_posix().casefold(),
                item.start,
                item.end,
            ),
        )
    ]
    fields = (
        ("alt_text", "markdown-alt"),
        ("nearby_caption", "markdown-caption"),
        ("nearest_heading", "markdown-heading"),
        ("nearby_paragraph", "markdown-paragraph"),
    )
    for field, reason in fields:
        for context in contexts:
            value = context[field]
            if value:
                return _normalized_visual_type("image", value), value, reason
    return "figure", "asset", "generic-fallback"


def _caption_parts(
    visual_type: str, semantic_text: str
) -> tuple[str, Optional[int], str]:
    match = CAPTION_LABEL_PATTERN.match(semantic_text)
    number = None
    if match is not None:
        number_text = match.group("number")
        number = int(number_text) if number_text else None
        semantic_text = semantic_text[match.end() :]
    prefix = {
        "table": "table",
        "chart": "chart",
    }.get(visual_type, "fig")
    semantic_text = semantic_text.strip(" \t\r\n.:：、-")
    relation = re.fullmatch(
        r"(.+?)\s+of\s+(?:the\s+)?(.+?)[.!?]?",
        semantic_text,
        re.IGNORECASE,
    )
    if relation is not None:
        semantic_text = "{} {}".format(
            relation.group(2), relation.group(1)
        )
    return prefix, number, semantic_text or "asset"


def _reference_sort_key(
    root: Path, record: AssetRecord
) -> tuple[str, int, str]:
    reference = min(
        record.references,
        key=lambda item: (
            item.markdown_path.relative_to(root).as_posix().casefold(),
            item.start,
            item.end,
        ),
    )
    return (
        reference.markdown_path.relative_to(root).as_posix().casefold(),
        reference.start,
        record.path.relative_to(root).as_posix().casefold(),
    )


def _document_slug_for_record(root: Path, record: AssetRecord) -> str:
    documents = {
        reference.markdown_path.relative_to(root).as_posix().casefold()
        for reference in record.references
    }
    if len(documents) > 1:
        return "shared"
    reference = min(
        record.references,
        key=lambda item: (
            item.markdown_path.relative_to(root).as_posix().casefold(),
            item.start,
            item.end,
        ),
    )
    document_path = reference.markdown_path.relative_to(root)
    return slugify(document_path.with_suffix("").as_posix()) or "document"


def propose_names(
    root: Path,
    assets: dict[Path, AssetRecord],
    metadata: dict[Path, list[dict[str, object]]],
) -> dict[Path, AssetRecord]:
    canonical_root = root.resolve(strict=False)
    ordered_records = sorted(
        assets.values(),
        key=lambda record: _reference_sort_key(canonical_root, record),
    )
    next_numbers = {"fig": 1, "table": 1, "chart": 1}
    used_targets: set[tuple[str, str]] = set()
    existing_targets: set[tuple[str, str]] = set()
    for directory in {record.path.parent for record in ordered_records}:
        try:
            children = directory.iterdir()
            for child in children:
                if child.is_file():
                    existing_targets.add(
                        (
                            str(directory).casefold(),
                            child.name.casefold(),
                        )
                    )
        except OSError:
            continue
    result: dict[Path, AssetRecord] = {}

    for record in ordered_records:
        visual_type, semantic_text, reason = choose_evidence(record, metadata)
        prefix, explicit_number, semantic_text = _caption_parts(
            visual_type, semantic_text
        )
        if explicit_number is None:
            number = next_numbers[prefix]
            next_numbers[prefix] += 1
        else:
            number = explicit_number
            next_numbers[prefix] = max(next_numbers[prefix], number + 1)

        document_slug = _document_slug_for_record(canonical_root, record)
        semantic_slug = slugify(semantic_text) or "asset"
        stem = "{}-{}{:02d}-{}".format(
            document_slug,
            prefix,
            number,
            semantic_slug,
        )
        hash8 = record.sha256[:8]
        candidate = _safe_filename_with_hashes(
            stem, record.path.suffix, [hash8]
        )
        collision_index = 0
        relative_asset = record.path.relative_to(canonical_root).as_posix()
        directory_key = str(record.path.parent).casefold()
        current_target = (directory_key, record.path.name.casefold())
        candidate_target = (directory_key, candidate.casefold())
        while (
            candidate_target in used_targets
            or (
                candidate_target in existing_targets
                and candidate_target != current_target
            )
        ):
            collision_index += 1
            collision_hash = hashlib.sha256(
                "{}:{}:{}".format(
                    record.sha256, relative_asset, collision_index
                ).encode("utf-8")
            ).hexdigest()[:8]
            candidate = _safe_filename_with_hashes(
                stem, record.path.suffix, [hash8, collision_hash]
            )
            candidate_target = (directory_key, candidate.casefold())
        used_targets.add(candidate_target)
        record.proposed_name = candidate
        record.reason = reason
        result[record.path] = record

    return {
        path: result[path]
        for path in sorted(result)
    }


def _relative_plan_path(path: Path, root: Path) -> str:
    return path.resolve(strict=False).relative_to(root).as_posix()


def _vision_context(record: AssetRecord, root: Path) -> dict[str, object]:
    references = []
    for reference in sorted(
        record.references,
        key=lambda item: (
            item.markdown_path.relative_to(root).as_posix().casefold(),
            item.start,
            item.end,
        ),
    ):
        references.append(
            {
                "document": reference.markdown_path.relative_to(root).as_posix(),
                "syntax": reference.syntax,
                "context": markdown_context(reference),
            }
        )
    return {
        "asset_path": record.path.relative_to(root).as_posix(),
        "original_name": record.path.name,
        "references": references,
    }


def _is_generic_vision_description(description: str) -> bool:
    slug = slugify(description)
    return slug in {
        "",
        "asset",
        "figure",
        "graphic",
        "image",
        "photo",
        "picture",
        "screenshot",
    }


def _vision_status_for_result(result: dict[str, object]) -> str:
    confidence = float(result.get("confidence", 0.0))
    description = str(result.get("description", ""))
    if confidence < VISION_CONFIDENCE_THRESHOLD:
        return "rejected"
    if _is_generic_vision_description(description):
        return "rejected"
    return "used"


def _vision_metadata(config: dict[str, object]) -> dict[str, object]:
    return {
        "vision": {
            "base_url_classification": config["base_url_classification"],
            "configured": bool(config["configured"]),
            "model": config["model"],
            "prompt_version": PROMPT_VERSION,
        }
    }


def _apply_optional_vision(
    root: Path,
    output_dir: Path,
    assets: dict[Path, AssetRecord],
    metadata: dict[Path, list[dict[str, object]]],
    vision_analyzer,
) -> tuple[dict[Path, str], dict[str, object], int]:
    config = load_vision_config()
    analyzer = vision_analyzer or analyze_image_with_vision
    cache = _load_vision_cache(output_dir)
    entries = cache["entries"]
    assert isinstance(entries, dict)
    status_by_path: dict[Path, str] = {}
    processed = 0

    for record in sorted(
        assets.values(),
        key=lambda item: _reference_sort_key(root, item),
    ):
        _visual_type, _semantic_text, reason = choose_evidence(
            record, metadata
        )
        if reason != "generic-fallback":
            continue
        processed += 1
        key = vision_cache_key(
            record.sha256,
            str(config["model"]),
            PROMPT_VERSION,
        )
        cached = entries.get(key)
        if isinstance(cached, dict):
            result = cached.get("result")
            try:
                validated = _validate_vision_result(result)
            except ValueError:
                validated = None
            if validated is not None:
                status = _vision_status_for_result(validated)
                status_by_path[record.path] = status
                if status == "used":
                    record.evidence = [
                        {
                            "caption": validated["description"],
                            "visual_type": "image",
                            "source": "vision",
                        }
                    ]
                continue
        try:
            result = _validate_vision_result(
                analyzer(record.path, _vision_context(record, root), config)
            )
        except Exception:
            status_by_path[record.path] = "failed"
            continue
        status = _vision_status_for_result(result)
        status_by_path[record.path] = status
        entries[key] = {
            "prompt_version": PROMPT_VERSION,
            "model": config["model"],
            "sha256": record.sha256,
            "result": result,
        }
        if status == "used":
            record.evidence = [
                {
                    "caption": result["description"],
                    "visual_type": "image",
                    "source": "vision",
                }
            ]

    _write_vision_cache(output_dir, cache)
    return status_by_path, config, processed


def check_vision() -> int:
    config = load_vision_config()
    status = {
        "api_key_configured": bool(config["configured"]),
        "base_url_classification": config["base_url_classification"],
        "model": config["model"],
        "prompt_version": PROMPT_VERSION,
    }
    print(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def create_plan(
    root: Path,
    output_dir: Path,
    use_vision: bool = False,
    vision_analyzer=None,
) -> dict[str, object]:
    canonical_root = root.resolve(strict=False)
    output_dir = output_dir.resolve(strict=False)
    documents, assets, warnings = build_asset_graph(canonical_root)
    metadata = load_mineru_metadata(canonical_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    vision_status_by_path: dict[Path, str] = {}
    vision_config = None
    vision_calls = 0
    if use_vision:
        vision_status_by_path, vision_config, vision_calls = (
            _apply_optional_vision(
                canonical_root,
                output_dir,
                assets,
                metadata,
                vision_analyzer,
            )
        )
    named_assets = propose_names(canonical_root, assets, metadata)

    entries = []
    for path, record in named_assets.items():
        old_path = _relative_plan_path(path, canonical_root)
        new_path = (
            path.parent / record.proposed_name
        ).relative_to(canonical_root).as_posix()
        references = [
            {
                "document": _relative_plan_path(
                    reference.markdown_path, canonical_root
                ),
                "start": reference.start,
                "end": reference.end,
                "syntax": reference.syntax,
            }
            for reference in sorted(
                record.references,
                key=lambda item: (
                    _relative_plan_path(
                        item.markdown_path, canonical_root
                    ).casefold(),
                    item.start,
                    item.end,
                ),
            )
        ]
        entries.append(
            {
                "old_path": old_path,
                "new_path": new_path,
                "sha256": record.sha256,
                "reason": record.reason,
                "references": references,
                "vision_status": (
                    vision_status_by_path.get(
                        path,
                        (
                            "needed"
                            if record.reason == "generic-fallback"
                            else "not-needed"
                        ),
                    )
                ),
            }
        )

    normalized_warnings = []
    for warning in warnings:
        warning_path = Path(warning["path"]).resolve(strict=False)
        path_text = (
            warning_path.relative_to(canonical_root).as_posix()
            if warning_path.is_relative_to(canonical_root)
            else warning_path.as_posix()
        )
        normalized_warnings.append(
            {"code": warning["code"], "path": path_text}
        )
    normalized_warnings.sort(
        key=lambda item: (item["code"], item["path"].casefold())
    )

    reference_count = 0
    for document in documents:
        reference_count += sum(
            reference.asset_path.suffix.casefold()
            in SUPPORTED_IMAGE_EXTENSIONS
            for reference in scan_markdown(document, canonical_root)
        )
    missing_count = sum(
        warning["code"] == "missing-asset"
        for warning in normalized_warnings
    )
    unreferenced_count = sum(
        warning["code"] == "unreferenced-asset"
        for warning in normalized_warnings
    )
    vision_needed = sum(
        entry["vision_status"] == "needed"
        for entry in entries
    )
    if use_vision:
        vision_needed = len(vision_status_by_path)
    plan = {
        "schema": 1,
        "assets": entries,
        "summary": {
            "documents": len(documents),
            "unique_references": reference_count,
            "eligible_assets": len(entries),
            "missing_assets": missing_count,
            "unreferenced_assets": unreferenced_count,
            "vision_needed_assets": vision_needed,
            "vision_calls": vision_calls,
            "warnings": len(normalized_warnings),
        },
        "warnings": normalized_warnings,
    }
    if use_vision and vision_config is not None:
        plan["metadata"] = _vision_metadata(vision_config)

    json_path = output_dir / "rename-plan.json"
    with json_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(
                plan,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        stream.write("\n")

    csv_path = output_dir / "rename-plan.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
                "old_path",
                "new_path",
                "sha256",
                "reason",
                "vision_status",
                "references",
            )
        )
        for entry in entries:
            writer.writerow(
                (
                    entry["old_path"],
                    entry["new_path"],
                    entry["sha256"],
                    entry["reason"],
                    entry["vision_status"],
                    json.dumps(
                        entry["references"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                )
            )
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely rename referenced Markdown assets."
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "check-vision",
        help="Show optional vision configuration without revealing secrets.",
    )
    args = parser.parse_args(argv)
    if args.command == "check-vision":
        return check_vision()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
