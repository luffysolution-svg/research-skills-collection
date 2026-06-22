import argparse
import hashlib
import html
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from urllib.parse import unquote


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
    for path in canonical_root.rglob("*.json"):
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely rename referenced Markdown assets."
    )
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
