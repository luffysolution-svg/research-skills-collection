import argparse
import hashlib
import html
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
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


def _merge_ranges(
    ranges: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _is_escaped(text: str, position: int) -> bool:
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return backslashes % 2 == 1


def protected_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    fence_pattern = re.compile(
        r"(?m)^(?P<prefix>(?: {0,3}>[ \t]?)* {0,3})"
        r"(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)(?:\r?\n|$)"
    )
    for opener in fence_pattern.finditer(text):
        if _overlaps(ranges, opener.start(), opener.end()):
            continue
        fence = opener.group("fence")
        if fence[0] == "`" and "`" in opener.group("info"):
            continue
        prefix = opener.group("prefix")
        closer_pattern = re.compile(
            rf"(?m)^{re.escape(prefix)}{re.escape(fence[0])}"
            rf"{{{len(fence)},}}[ \t]*(?=\r?$)"
        )
        closer = closer_pattern.search(text, opener.end())
        end = closer.end() if closer else len(text)
        ranges.append((opener.start(), end))

    ranges = _merge_ranges(ranges)
    position = 0
    while position < len(text):
        start = text.find("<!--", position)
        if start == -1:
            break
        if _overlaps(ranges, start, start + 4):
            position = start + 4
            continue
        end = text.find("-->", start + 4)
        while end != -1 and _overlaps(ranges, end, end + 3):
            end = text.find("-->", end + 3)
        end = end + 3 if end != -1 else len(text)
        ranges.append((start, end))
        ranges = _merge_ranges(ranges)
        position = end

    position = 0
    while position < len(text):
        opener = re.search(r"`+", text[position:])
        if not opener:
            break
        start = position + opener.start()
        run = opener.group()
        if (
            _is_escaped(text, start)
            or _overlaps(ranges, start, start + len(run))
        ):
            position = start + len(run)
            continue
        search_from = start + len(run)
        end = text.find(run, search_from)
        while end != -1 and (
            _is_escaped(text, end)
            or _overlaps(ranges, end, end + len(run))
            or (end > 0 and text[end - 1] == "`")
            or (
                end + len(run) < len(text)
                and text[end + len(run)] == "`"
            )
        ):
            end = text.find(run, end + len(run))
        if end == -1:
            position = search_from
            continue
        ranges.append((start, end + len(run)))
        ranges = _merge_ranges(ranges)
        position = end + len(run)

    return ranges


def _without_url_suffix(destination: str) -> str:
    for position, character in enumerate(destination):
        if character in "?#" and not _is_escaped(destination, position):
            return destination[:position]
    return destination


def destination_to_asset(
    markdown_path: Path, root: Path, raw_destination: str
) -> tuple[str, Path] | None:
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
) -> tuple[int, int] | None:
    position = opening_parenthesis + 1
    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    if position >= len(text):
        return None

    if text[position] == "<":
        start = position + 1
        position = start
        while position < len(text):
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


def _closing_bracket(text: str, opening_bracket: int) -> int | None:
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
