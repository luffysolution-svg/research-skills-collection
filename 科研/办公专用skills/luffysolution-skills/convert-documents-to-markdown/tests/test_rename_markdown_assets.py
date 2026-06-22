import ast
import importlib.util
import io
import json
import sys
import tempfile
import tokenize
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "rename-markdown-assets.py"
SPEC = importlib.util.spec_from_file_location("rename_markdown_assets", SCRIPT_PATH)
rename_markdown_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rename_markdown_assets)


def parenthesized_multi_with_lines(source):
    ignored = {
        tokenize.COMMENT,
        tokenize.ENCODING,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    expect_context = False
    found = []
    for token in tokens:
        if token.type in ignored:
            continue
        if expect_context:
            if token.type == tokenize.OP and token.string == "(":
                found.append(token.start[0])
            expect_context = False
        elif token.type == tokenize.NAME and token.string == "with":
            expect_context = True
    return found


class RenameMarkdownAssetsTests(unittest.TestCase):
    def make_markdown_tree(self, temp_dir, markdown):
        root = Path(temp_dir)
        images = root / "docs" / "images"
        images.mkdir(parents=True)
        markdown_path = root / "docs" / "report.md"
        markdown_path.write_text(markdown, encoding="utf-8", newline="")
        return root, images, markdown_path

    def write_json(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_sources_avoid_python_3_10_only_syntax(self):
        for path in (SCRIPT_PATH, Path(__file__)):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(
                source,
                filename=str(path),
                feature_version=9,
            )
            annotations = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    annotations.append(node.returns)
                    annotations.extend(
                        argument.annotation
                        for argument in (
                            list(node.args.posonlyargs)
                            + list(node.args.args)
                            + list(node.args.kwonlyargs)
                        )
                    )
                    if node.args.vararg is not None:
                        annotations.append(node.args.vararg.annotation)
                    if node.args.kwarg is not None:
                        annotations.append(node.args.kwarg.annotation)
                elif isinstance(node, ast.AnnAssign):
                    annotations.append(node.annotation)
            pep604_annotations = [
                annotation
                for annotation in annotations
                if annotation is not None
                and any(
                    isinstance(item, ast.BinOp)
                    and isinstance(item.op, ast.BitOr)
                    for item in ast.walk(annotation)
                )
            ]
            self.assertEqual(pep604_annotations, [], str(path))
            self.assertEqual(
                parenthesized_multi_with_lines(source),
                [],
                str(path),
            )

    def test_parenthesized_multi_with_detector_handles_layouts(self):
        self.assertEqual(
            parenthesized_multi_with_lines("with (a, b):\n    pass\n"),
            [1],
        )
        self.assertEqual(
            parenthesized_multi_with_lines(
                "with (\n"
                "    a,\n"
                "    b,\n"
                "):\n"
                "    pass\n"
            ),
            [1],
        )
        self.assertEqual(
            parenthesized_multi_with_lines(
                "with open('a') as stream:\n"
                "    pass\n"
            ),
            [],
        )

    def test_sha256_file_returns_full_lowercase_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset_path = Path(temp_dir) / "asset.bin"
            asset_path.write_bytes(b"asset")

            digest = rename_markdown_assets.sha256_file(asset_path)

        self.assertEqual(
            digest,
            "d59386e0ae435e292fbe0ebcdb954b75ed5fb3922091277cb19f798fc5d50718",
        )

    def test_slugify_normalizes_caption_to_kebab_case(self):
        self.assertEqual(
            rename_markdown_assets.slugify(
                "Figure 1: First Reactor Temperature Profile"
            ),
            "figure-1-first-reactor-temperature-profile",
        )

    def test_safe_filename_uses_asset_for_windows_reserved_name(self):
        self.assertEqual(
            rename_markdown_assets.safe_filename("CON", ".jpg", "12345678"),
            "asset-12345678.jpg",
        )

    def test_safe_filename_truncates_to_limit_and_preserves_suffix(self):
        filename = rename_markdown_assets.safe_filename(
            "a" * 300, ".png", "89abcdef", limit=80
        )

        self.assertLessEqual(len(filename), 80)
        self.assertTrue(filename.endswith("-89abcdef.png"))

    def test_scan_markdown_finds_inline_reference_and_html_images(self):
        markdown = (
            '![inline](images/a%20b.jpg "title")\n'
            "![reference][plot]\n"
            '[plot]: <images/c 图.png> "caption"\n'
            '<IMG alt="chart" SRC="images/chart.jpg"/>\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            for name in ("a b.jpg", "c 图.png", "chart.jpg"):
                (images / name).write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [
                (reference.syntax, reference.decoded_destination)
                for reference in references
            ],
            [
                ("markdown-inline", "images/a b.jpg"),
                ("markdown-reference", "images/c 图.png"),
                ("html-img", "images/chart.jpg"),
            ],
        )
        self.assertEqual(
            [reference.encoding_style for reference in references],
            ["percent", "raw", "raw"],
        )

    def test_scan_markdown_ignores_protected_ranges_and_remote_urls(self):
        markdown = (
            "`![inline](images/inline-code.png)`\n"
            "~~~md\n![fenced](images/fenced.png)\n~~~\n"
            "<!-- <img src='images/comment.png'> -->\n"
            "![remote](https://example.com/remote.png)\n"
            '<img src="data:image/png;base64,AAAA">\n'
            "![local](images/local.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            for name in (
                "inline-code.png",
                "fenced.png",
                "comment.png",
                "local.png",
            ):
                (images / name).write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [
                (reference.syntax, reference.decoded_destination)
                for reference in references
            ],
            [("markdown-inline", "images/local.png")],
        )

    def test_scan_markdown_does_not_treat_data_src_as_src(self):
        markdown = (
            '<img data-src="images/lazy.png" alt="lazy">\n'
            '<img custom.src="images/custom.png" alt="custom">\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "lazy.png").write_bytes(b"asset")
            (images / "custom.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(references, [])

    def test_scan_markdown_parses_img_after_quoted_greater_than(self):
        markdown = '<img alt="value > threshold" src="images/chart.png">\n'
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "chart.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )
            encoded_markdown = markdown_path.read_bytes()

        self.assertEqual(len(references), 1)
        reference = references[0]
        self.assertEqual(reference.raw_destination, "images/chart.png")
        self.assertEqual(
            encoded_markdown[reference.start : reference.end],
            b"images/chart.png",
        )

    def test_scan_markdown_normalizes_html_entity_query_and_fragment(self):
        raw_destination = "images/a&amp;b.png?width=200#preview"
        markdown = f'<img src="{raw_destination}">\n'
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "a&b.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )
            encoded_markdown = markdown_path.read_bytes()

        self.assertEqual(len(references), 1)
        reference = references[0]
        self.assertEqual(reference.raw_destination, raw_destination)
        self.assertEqual(reference.decoded_destination, "images/a&b.png")
        self.assertEqual(reference.asset_path, images / "a&b.png")
        self.assertEqual(
            encoded_markdown[reference.start : reference.end].decode(),
            raw_destination,
        )

    def test_scan_markdown_rejects_destinations_empty_after_url_normalization(self):
        markdown = (
            "![fragment](#preview)\n"
            "![query](?width=2)\n"
            '<img src="">\n'
            "![valid](images/valid.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "valid.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/valid.png"],
        )

    def test_scan_markdown_records_utf8_byte_offsets_for_cjk_and_crlf(self):
        markdown = (
            "标题\r\n"
            "![图](images/反应器%20图.png)\r\n"
            '<img src="images/曲线 图.jpg">\r\n'
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "反应器 图.png").write_bytes(b"asset")
            (images / "曲线 图.jpg").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )
            encoded_markdown = markdown_path.read_bytes()

        self.assertEqual(
            [
                encoded_markdown[reference.start : reference.end].decode(
                    "utf-8"
                )
                for reference in references
            ],
            ["images/反应器%20图.png", "images/曲线 图.jpg"],
        )
        self.assertEqual(
            [reference.raw_destination for reference in references],
            ["images/反应器%20图.png", "images/曲线 图.jpg"],
        )

    def test_scan_markdown_uses_only_referenced_definitions(self):
        markdown = (
            "![used][plot]\n"
            "[plot]: images/used.png\n"
            "[unused]: images/unused.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "used.png").write_bytes(b"asset")
            (images / "unused.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/used.png"],
        )

    def test_scan_markdown_supports_escaped_closing_bracket_in_definition_label(self):
        markdown = (
            "![escaped label][a\\]]\n"
            "[a\\]]: images/a.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "a.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/a.png"],
        )

    def test_reference_definition_destination_may_follow_indented_line(self):
        markdown = (
            "![plot]\n"
            "[plot]:\n"
            "  images/a.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "a.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/a.png"],
        )

    def test_scan_markdown_shortcut_uses_first_normalized_definition(self):
        markdown = (
            "![Plot   Name]\n"
            "[ plot name ]: images/first.png\n"
            "[PLOT NAME]: images/second.png\n"
            "![Collapsed   Label][]\n"
            "[collapsed label]: images/collapsed.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "first.png").write_bytes(b"asset")
            (images / "second.png").write_bytes(b"asset")
            (images / "collapsed.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/first.png", "images/collapsed.png"],
        )

    def test_scan_markdown_ignores_escaped_image_markers(self):
        markdown = (
            "\\![inline](images/escaped-inline.png)\n"
            "\\![reference][plot]\n"
            "[plot]: images/escaped-reference.png\n"
            "![local](images/local.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            for name in (
                "escaped-inline.png",
                "escaped-reference.png",
                "local.png",
            ):
                (images / name).write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/local.png"],
        )

    def test_scan_markdown_unescapes_local_destination_spaces(self):
        markdown = "![space](images/a\\ b.png)\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "a b.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].raw_destination, "images/a\\ b.png")
        self.assertEqual(
            references[0].decoded_destination, "images/a b.png"
        )
        self.assertEqual(references[0].asset_path, images / "a b.png")

    def test_scan_markdown_rejects_inline_images_without_closing_parenthesis(self):
        markdown = (
            "![plain](images/plain.png\n"
            '![title](images/title.png "caption"\n'
            "![valid](images/valid.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            for name in ("plain.png", "title.png", "valid.png"):
                (images / name).write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/valid.png"],
        )

    def test_inline_code_comment_marker_does_not_open_html_comment(self):
        markdown = (
            "`<!--`\n"
            "![after](images/after.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "after.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/after.png"],
        )

    def test_angle_inline_destination_cannot_cross_line_ending(self):
        markdown = (
            "![invalid](<images/a\nb.png>)\n"
            "![valid](images/valid.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "valid.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/valid.png"],
        )

    def test_scan_markdown_preserves_escaped_fragment_character(self):
        markdown = "![hash](images/a\\#b.png)\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "a#b.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(len(references), 1)
        self.assertEqual(
            references[0].decoded_destination, "images/a#b.png"
        )
        self.assertEqual(references[0].asset_path, images / "a#b.png")

    def test_escaped_backticks_do_not_protect_image_syntax(self):
        markdown = "\\` ![local](images/local.png) \\`\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "local.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/local.png"],
        )

    def test_scan_markdown_handles_nested_and_escaped_alt_brackets(self):
        markdown = (
            "![outer [inner\\] value]](images/nested.png)\n"
            "![plot \\[draft\\]][plot]\n"
            "[plot]: images/reference.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "nested.png").write_bytes(b"asset")
            (images / "reference.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/nested.png", "images/reference.png"],
        )

    def test_scan_markdown_rejects_path_traversal(self):
        markdown = (
            "![traversal](../../outside.png)\n"
            "![safe](images/safe.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "safe.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/safe.png"],
        )

    def test_scan_markdown_rejects_symlink_escapes(self):
        markdown = (
            "![symlink](images/link/secret.png)\n"
            "![safe](images/safe.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            outside = root.parent / f"{root.name}-outside-assets"
            outside.mkdir()
            self.addCleanup(
                lambda: outside.rmdir() if outside.exists() else None
            )
            (outside / "secret.png").write_bytes(b"secret")
            self.addCleanup(
                lambda: (outside / "secret.png").unlink(missing_ok=True)
            )
            try:
                (images / "link").symlink_to(
                    outside, target_is_directory=True
                )
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            (images / "safe.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/safe.png"],
        )

    def test_destination_to_asset_rejects_mocked_canonical_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown_path = root / "docs" / "report.md"
            candidate = root / "docs" / "images" / "link" / "secret.png"
            outside = root.parent / "outside" / "secret.png"
            real_resolve = Path.resolve

            def resolve_with_escape(path, strict=False):
                if path == candidate:
                    return outside
                return real_resolve(path, strict=strict)

            with patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=resolve_with_escape,
            ):
                result = rename_markdown_assets.destination_to_asset(
                    markdown_path, root, "images/link/secret.png"
                )

        self.assertIsNone(result)

    def test_scan_markdown_does_not_require_asset_to_exist(self):
        markdown = "![future](images/not-created-yet.png)\n"
        with tempfile.TemporaryDirectory() as temp_dir:
            root, _images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(len(references), 1)
        self.assertEqual(
            references[0].asset_path,
            markdown_path.parent / "images" / "not-created-yet.png",
        )

    def test_protected_ranges_cover_fences_inline_code_and_comments(self):
        markdown = (
            "before `inline` after\n"
            "````python\nfenced\n````\n"
            "<!-- comment -->"
        )

        ranges = rename_markdown_assets.protected_ranges(markdown)
        protected_text = [markdown[start:end] for start, end in ranges]

        self.assertEqual(
            protected_text,
            ["`inline`", "````python\nfenced\n````", "<!-- comment -->"],
        )

    def test_fenced_comment_does_not_protect_content_after_fence(self):
        markdown = (
            "```\n"
            "<!-- unclosed inside fence\n"
            "```\n"
            "![after](images/after.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "after.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/after.png"],
        )

    def test_inline_code_does_not_use_closer_inside_fenced_code(self):
        markdown = (
            "`unclosed inline\n"
            "```\n"
            "` closer inside fence\n"
            "```\n"
        )

        ranges = rename_markdown_assets.protected_ranges(markdown)
        protected_text = [markdown[start:end] for start, end in ranges]

        self.assertEqual(
            protected_text,
            ["```\n` closer inside fence\n```"],
        )

    def test_blockquoted_fence_protects_images(self):
        markdown = (
            "> ~~~markdown\n"
            "> ![inside tilde](images/inside-tilde.png)\n"
            "> ~~~\n"
            "> ```markdown\n"
            "> ![inside backtick](images/inside-backtick.png)\n"
            "> ```\n"
            "![outside](images/outside.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "inside-tilde.png").write_bytes(b"asset")
            (images / "inside-backtick.png").write_bytes(b"asset")
            (images / "outside.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/outside.png"],
        )

    def test_blockquoted_fence_closer_allows_spacing_and_longer_marker(self):
        markdown = (
            "> ```md\n"
            "> ![inside](images/inside.png)\n"
            ">````\n"
            "![outside](images/outside.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "inside.png").write_bytes(b"asset")
            (images / "outside.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/outside.png"],
        )

    def test_backtick_in_fence_info_does_not_open_fence(self):
        markdown = (
            "```python`invalid\n"
            "![visible](images/visible.png)\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "visible.png").write_bytes(b"asset")

            references = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )

        self.assertEqual(
            [reference.decoded_destination for reference in references],
            ["images/visible.png"],
        )

    def test_graph_tracks_shared_missing_and_unreferenced_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            docs = root / "docs"
            images.mkdir()
            docs.mkdir()
            shared = images / "shared.jpg"
            shared.write_bytes(b"shared")
            unreferenced = images / "unused.png"
            unreferenced.write_bytes(b"unused")
            first = docs / "a.md"
            second = docs / "b.md"
            first.write_text(
                "![shared](../images/shared.jpg)\n"
                "![missing](../images/missing.png)\n",
                encoding="utf-8",
            )
            second.write_text(
                "![shared again](../images/shared.jpg)\n",
                encoding="utf-8",
            )

            documents, assets, warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

        shared_path = shared.resolve()
        self.assertEqual(documents, [first, second])
        self.assertEqual(list(assets), [shared_path])
        self.assertEqual(len(assets[shared_path].references), 2)
        self.assertEqual(
            [warning["code"] for warning in warnings],
            ["missing-asset", "unreferenced-asset"],
        )
        self.assertEqual(
            [warning["path"] for warning in warnings],
            [
                str((images / "missing.png").resolve()),
                str(unreferenced.resolve()),
            ],
        )

    def test_content_list_normalizes_image_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "shared.jpg"
            image.parent.mkdir()
            image.write_bytes(b"shared")
            metadata_path = root / "content_list.json"
            self.write_json(
                metadata_path,
                [
                    {
                        "type": "image",
                        "img_path": "images/shared.jpg",
                        "image_caption": [
                            "Figure 1. Temperature profile"
                        ],
                        "page_idx": 2,
                        "bbox": [10, 20, 30, 40],
                    }
                ],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        evidence = metadata[image.resolve()][0]
        self.assertEqual(
            evidence,
            {
                "path": str(image.resolve()),
                "caption": "Figure 1. Temperature profile",
                "visual_type": "image",
                "page_idx": 2,
                "bbox": [10, 20, 30, 40],
                "source": "content_list",
            },
        )

    def test_content_list_v2_normalizes_nested_content_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "shared.webp"
            image.parent.mkdir()
            image.write_bytes(b"shared")
            metadata_path = root / "content_list_v2.json"
            self.write_json(
                metadata_path,
                {
                    "content": [
                        {
                            "content": {
                                "image_path": "images/shared.webp",
                                "caption": "Figure 1. Temperature profile",
                                "sub_type": "image",
                                "page_idx": 2,
                                "bbox": [1, 2, 3, 4],
                            }
                        }
                    ]
                },
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        evidence = metadata[image.resolve()][0]
        self.assertEqual(
            set(evidence),
            {
                "path",
                "caption",
                "visual_type",
                "page_idx",
                "bbox",
                "source",
            },
        )
        self.assertEqual(evidence["caption"], "Figure 1. Temperature profile")
        self.assertEqual(evidence["visual_type"], "image")
        self.assertEqual(evidence["page_idx"], 2)
        self.assertEqual(evidence["bbox"], [1, 2, 3, 4])
        self.assertEqual(evidence["source"], "content_list_v2")

    def test_supported_image_extensions_are_case_insensitive(self):
        expected = {
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

        self.assertEqual(
            rename_markdown_assets.SUPPORTED_IMAGE_EXTENSIONS,
            expected,
        )
        self.assertTrue(
            all(
                suffix.upper().lower()
                in rename_markdown_assets.SUPPORTED_IMAGE_EXTENSIONS
                for suffix in expected
            )
        )

    def test_unreferenced_warnings_ignore_unrelated_image_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "docs" / "images"
            unrelated = root / "website" / "assets"
            images.mkdir(parents=True)
            unrelated.mkdir(parents=True)
            referenced = images / "used.PNG"
            referenced.write_bytes(b"used")
            local_unused = images / "unused.TIFF"
            local_unused.write_bytes(b"unused")
            unrelated_image = unrelated / "logo.png"
            unrelated_image.write_bytes(b"logo")
            markdown = root / "docs" / "report.md"
            markdown.write_text(
                "![used](images/used.PNG)\n",
                encoding="utf-8",
            )

            _documents, _assets, warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

        unreferenced_paths = {
            warning["path"]
            for warning in warnings
            if warning["code"] == "unreferenced-asset"
        }
        self.assertEqual(unreferenced_paths, {str(local_unused.resolve())})
        self.assertNotIn(str(unrelated_image.resolve()), unreferenced_paths)

    def test_discovers_exact_and_prefixed_content_list_variants(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            images.mkdir()
            filenames = [
                "content_list.json",
                "content_list_v2.json",
                "alpha_content_list.json",
                "beta_content_list_v2.json",
            ]
            expected_sources = []
            for index, filename in enumerate(filenames):
                image = images / f"{index}.png"
                image.write_bytes(str(index).encode())
                self.write_json(
                    root / filename,
                    [{"img_path": f"images/{index}.png"}],
                )
                expected_sources.append(Path(filename).stem)
            self.write_json(
                root / "not_content_list_v3.json",
                [{"img_path": "images/0.png", "caption": "ignored"}],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(
            [
                evidence[0]["source"]
                for _path, evidence in sorted(metadata.items())
            ],
            expected_sources,
        )

    def test_metadata_files_discovery_is_case_insensitive_on_case_sensitive_fs(
        self,
    ):
        root = Path("C:/workspace").resolve(strict=False)
        uppercase = root / "CONTENT_LIST.JSON"
        mixed = root / "report_content_list.JSON"
        ignored = root / "notes.JSON"
        real_resolve = Path.resolve

        def resolve_candidates(path, strict=False):
            return real_resolve(path, strict=strict)

        def rglob_candidates(path, pattern):
            self.assertEqual(pattern, "*")
            return [ignored, mixed, uppercase]

        with patch.object(
            Path,
            "rglob",
            autospec=True,
            side_effect=rglob_candidates,
        ):
            with patch.object(
                Path, "is_file", autospec=True, return_value=True
            ):
                with patch.object(
                    Path,
                    "resolve",
                    autospec=True,
                    side_effect=resolve_candidates,
                ):
                    metadata_files = rename_markdown_assets._metadata_files(
                        root
                    )

        self.assertEqual(metadata_files, sorted([uppercase, mixed]))

    def test_content_list_v2_merges_parent_path_with_nested_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "shared.png"
            image.parent.mkdir()
            image.write_bytes(b"shared")
            self.write_json(
                root / "report_content_list_v2.json",
                [
                    {
                        "img_path": "images/shared.png",
                        "content": {
                            "image_caption": ["Merged caption"],
                            "page_idx": "3",
                            "bbox": [1, 2.5, 3, 4],
                            "sub_type": "chart",
                        },
                    }
                ],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(
            metadata[image.resolve()],
            [
                {
                    "path": str(image.resolve()),
                    "caption": "Merged caption",
                    "visual_type": "chart",
                    "page_idx": 3,
                    "bbox": [1, 2.5, 3, 4],
                    "source": "report_content_list_v2",
                }
            ],
        )

    def test_metadata_accepts_missing_optional_fields_with_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "valid.png"
            image.parent.mkdir()
            image.write_bytes(b"valid")
            self.write_json(
                root / "content_list.json",
                [{"img_path": "images/valid.png"}],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(
            metadata[image.resolve()],
            [
                {
                    "path": str(image.resolve()),
                    "caption": "",
                    "visual_type": "image",
                    "page_idx": None,
                    "bbox": None,
                    "source": "content_list",
                }
            ],
        )

    def test_metadata_skips_records_with_explicit_invalid_optional_fields(self):
        invalid_fields = [
            ("caption-object", {"caption": {"bad": "shape"}}),
            ("caption-number", {"caption": 7}),
            ("caption-mixed-list", {"caption": ["valid", 7]}),
            ("type-list", {"type": ["image"]}),
            ("type-object", {"visual_type": {"kind": "image"}}),
            ("type-empty", {"sub_type": ""}),
            ("page-negative", {"page_idx": -1}),
            ("page-negative-float", {"page_index": -1.0}),
            ("page-fractional-float", {"page_index": 4.5}),
            ("page-nan", {"page_index": float("nan")}),
            ("page-infinity", {"page_index": float("inf")}),
            ("page-bool", {"page": True}),
            ("page-spaced-string", {"page_idx": " 4 "}),
            ("page-signed-string", {"page_idx": "+4"}),
            ("page-decimal-string", {"page_idx": "4.0"}),
            ("bbox-object", {"bbox": {"left": 1}}),
            ("bbox-empty", {"bbox": []}),
            ("bbox-bool", {"bbox": [1, True, 3, 4]}),
            ("bbox-nan", {"bbox": [1, float("nan"), 3, 4]}),
            ("bbox-infinity", {"bbox": [1, float("inf"), 3, 4]}),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            images.mkdir()
            records = []
            for name, fields in invalid_fields:
                image = images / f"{name}.png"
                image.write_bytes(name.encode())
                records.append(
                    {"img_path": f"images/{image.name}", **fields}
                )
            self.write_json(root / "content_list.json", records)

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(metadata, {})

    def test_metadata_accepts_integral_float_page_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "valid.png"
            image.parent.mkdir()
            image.write_bytes(b"valid")
            self.write_json(
                root / "content_list.json",
                [
                    {
                        "img_path": "images/valid.png",
                        "page_index": 4.0,
                    }
                ],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(metadata[image.resolve()][0]["page_idx"], 4)

    def test_metadata_skips_oversized_page_string_and_loads_later_record(self):
        original_limit = (
            sys.get_int_max_str_digits()
            if hasattr(sys, "get_int_max_str_digits")
            else None
        )
        try:
            if hasattr(sys, "set_int_max_str_digits"):
                sys.set_int_max_str_digits(0)
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                images = root / "images"
                images.mkdir()
                invalid = images / "invalid.png"
                valid = images / "valid.png"
                invalid.write_bytes(b"invalid")
                valid.write_bytes(b"valid")
                self.write_json(
                    root / "content_list.json",
                    [
                        {
                            "img_path": "images/invalid.png",
                            "page_idx": "9" * 5000,
                        },
                        {
                            "img_path": "images/valid.png",
                            "page_idx": 3,
                        },
                    ],
                )

                metadata = rename_markdown_assets.load_mineru_metadata(root)
        finally:
            if original_limit is not None:
                sys.set_int_max_str_digits(original_limit)

        self.assertNotIn(invalid.resolve(), metadata)
        self.assertEqual(metadata[valid.resolve()][0]["page_idx"], 3)

    def test_metadata_skips_oversized_bbox_int_and_loads_later_record(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            images.mkdir()
            invalid = images / "invalid.png"
            valid = images / "valid.png"
            invalid.write_bytes(b"invalid")
            valid.write_bytes(b"valid")
            oversized_integer = "1" + "0" * 10000
            (root / "content_list.json").write_text(
                "["
                '{"img_path":"images/invalid.png","bbox":[0,'
                + oversized_integer
                + ',2,3]},'
                '{"img_path":"images/valid.png","bbox":[0,1,2,3]}'
                "]",
                encoding="utf-8",
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertNotIn(invalid.resolve(), metadata)
        self.assertEqual(
            metadata[valid.resolve()][0]["bbox"],
            [0, 1, 2, 3],
        )

    def test_metadata_skips_deeply_nested_file_and_loads_later_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "valid.png"
            image.parent.mkdir()
            image.write_bytes(b"valid")
            depth = 2000
            (root / "a_content_list.json").write_text(
                "[" * depth + "0" + "]" * depth,
                encoding="utf-8",
            )
            self.write_json(
                root / "b_content_list.json",
                [{"img_path": "images/valid.png", "page_idx": 2}],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(metadata[image.resolve()][0]["page_idx"], 2)

    def test_metadata_traversal_failure_discards_staged_file_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            images.mkdir()
            partial = images / "partial.png"
            valid = images / "valid.png"
            partial.write_bytes(b"partial")
            valid.write_bytes(b"valid")
            self.write_json(
                root / "a_content_list.json",
                {"marker": "fail-during-traversal"},
            )
            self.write_json(
                root / "b_content_list.json",
                {"marker": "valid"},
            )

            def records(value, inherited=None):
                if value["marker"] == "fail-during-traversal":
                    yield {
                        "img_path": "images/partial.png",
                        "page_idx": 1,
                    }
                    raise RecursionError("nested metadata traversal")
                yield {
                    "img_path": "images/valid.png",
                    "page_idx": 2,
                }

            with patch.object(
                rename_markdown_assets,
                "_metadata_records",
                new=records,
            ):
                metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertNotIn(partial.resolve(), metadata)
        self.assertEqual(metadata[valid.resolve()][0]["page_idx"], 2)

    def test_metadata_skips_invalid_asset_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_json(
                root / "content_list.json",
                [
                    {"img_path": ""},
                    {"img_path": "images/bad\u0000.png"},
                    {"img_path": "images/not-supported.txt"},
                ],
            )

            metadata = rename_markdown_assets.load_mineru_metadata(root)

        self.assertEqual(metadata, {})

    def test_metadata_files_reject_canonical_escapes_and_deduplicate_aliases(
        self,
    ):
        root = Path("C:/workspace").resolve(strict=False)
        alias = root / "alias_content_list.json"
        second_alias = root / "second_content_list_v2.json"
        metadata = root / "data.json"
        outside_link = root / "outside_content_list.json"
        outside = Path("C:/outside/data.json").resolve(strict=False)
        real_resolve = Path.resolve

        def resolve_candidates(path, strict=False):
            if path in (alias, second_alias):
                return metadata
            if path == outside_link:
                return outside
            return real_resolve(path, strict=strict)

        with patch.object(
            Path,
            "rglob",
            autospec=True,
            return_value=[outside_link, second_alias, alias],
        ):
            with patch.object(
                Path, "is_file", autospec=True, return_value=True
            ):
                with patch.object(
                    Path,
                    "resolve",
                    autospec=True,
                    side_effect=resolve_candidates,
                ):
                    metadata_files = rename_markdown_assets._metadata_files(
                        root
                    )

        self.assertEqual(metadata_files, [metadata])

    def test_unreferenced_scan_prunes_nested_referenced_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            nested = images / "nested"
            nested.mkdir(parents=True)
            (images / "parent.png").write_bytes(b"parent")
            (nested / "child.png").write_bytes(b"child")
            (root / "report.md").write_text(
                "![parent](images/parent.png)\n"
                "![child](images/nested/child.png)\n",
                encoding="utf-8",
            )
            real_rglob = Path.rglob
            scanned = []

            def tracking_rglob(path, pattern):
                scanned.append((path.resolve(strict=False), pattern))
                return real_rglob(path, pattern)

            with patch.object(
                Path,
                "rglob",
                autospec=True,
                side_effect=tracking_rglob,
            ):
                rename_markdown_assets.build_asset_graph(root)

        self.assertIn((images.resolve(), "*"), scanned)
        self.assertNotIn((nested.resolve(), "*"), scanned)

    def test_missing_root_asset_does_not_expand_unreferenced_scan_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            markdown = root / "report.md"
            markdown.write_text("![missing](missing.png)\n", encoding="utf-8")
            unrelated = root / "unrelated.png"
            unrelated.write_bytes(b"unrelated")

            _documents, _assets, warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

        self.assertEqual(
            warnings,
            [
                {
                    "code": "missing-asset",
                    "path": str((root / "missing.png").resolve()),
                }
            ],
        )

    def test_iter_markdown_files_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            docs.mkdir()
            lower = docs / "a.md"
            upper = docs / "B.MD"
            lower.write_text("lower", encoding="utf-8")
            upper.write_text("upper", encoding="utf-8")

            documents = rename_markdown_assets.iter_markdown_files(root)

        self.assertEqual(
            documents,
            sorted([lower.resolve(), upper.resolve()]),
        )

    def test_iter_markdown_files_rejects_canonical_escapes_and_deduplicates(
        self,
    ):
        root = Path("C:/workspace").resolve(strict=False)
        lower = root / "docs" / "a.md"
        alias = root / "docs" / "alias.md"
        outside_link = root / "docs" / "outside.md"
        outside = Path("C:/outside.md").resolve(strict=False)
        real_resolve = Path.resolve

        def resolve_candidates(path, strict=False):
            if path == alias:
                return lower
            if path == outside_link:
                return outside
            return real_resolve(path, strict=strict)

        with patch.object(
            Path,
            "rglob",
            autospec=True,
            return_value=[outside_link, alias, lower],
        ):
            with patch.object(
                Path, "is_file", autospec=True, return_value=True
            ):
                with patch.object(
                    Path,
                    "resolve",
                    autospec=True,
                    side_effect=resolve_candidates,
                ):
                    documents = rename_markdown_assets.iter_markdown_files(
                        root
                    )

        self.assertEqual(documents, [lower])

    def test_graph_attaches_ordered_metadata_and_hashes_shared_asset_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = root / "images"
            docs = root / "docs"
            images.mkdir()
            docs.mkdir()
            shared = images / "shared.png"
            shared.write_bytes(b"shared")
            (docs / "a.md").write_text(
                "![one](../images/shared.png)\n",
                encoding="utf-8",
            )
            (docs / "b.MD").write_text(
                "![two](../images/shared.png)\n",
                encoding="utf-8",
            )
            self.write_json(
                root / "b_content_list_v2.json",
                [
                    {
                        "img_path": "images/shared.png",
                        "caption": "second",
                    }
                ],
            )
            self.write_json(
                root / "a_content_list.json",
                [
                    {
                        "img_path": "images/shared.png",
                        "caption": "first",
                    },
                    {
                        "img_path": "images/shared.png",
                        "caption": "first",
                    },
                ],
            )

            with patch.object(
                rename_markdown_assets,
                "sha256_file",
                wraps=rename_markdown_assets.sha256_file,
            ) as hash_file:
                _documents, assets, _warnings = (
                    rename_markdown_assets.build_asset_graph(root)
                )

        record = assets[shared.resolve()]
        self.assertEqual(len(record.references), 2)
        self.assertEqual(
            [
                (item["source"], item["caption"])
                for item in record.evidence
            ],
            [
                ("a_content_list", "first"),
                ("b_content_list_v2", "second"),
            ],
        )
        hash_file.assert_called_once_with(shared.resolve())

    def test_markdown_context_uses_byte_offsets_and_stable_fallback_order(self):
        markdown = (
            "# Reactor Results\n\n"
            "The experiment reached steady state after ten minutes.\n\n"
            "前缀文字\n"
            "![Outlet temperature](images/reactor.png)\n"
            "Figure 7. Temperature profile near the outlet.\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "reactor.png").write_bytes(b"reactor")
            reference = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )[0]

            context = rename_markdown_assets.markdown_context(reference)
            record = rename_markdown_assets.AssetRecord(
                path=reference.asset_path,
                sha256="a" * 64,
                references=[reference],
                evidence=[],
            )
            selected = rename_markdown_assets.choose_evidence(record, {})

        self.assertEqual(context["alt_text"], "Outlet temperature")
        self.assertEqual(
            context["nearby_caption"],
            "Figure 7. Temperature profile near the outlet.",
        )
        self.assertEqual(context["nearest_heading"], "Reactor Results")
        self.assertEqual(
            context["nearby_paragraph"],
            "The experiment reached steady state after ten minutes.",
        )
        self.assertEqual(
            selected,
            ("figure", "Outlet temperature", "markdown-alt"),
        )

    def test_choose_evidence_prefers_mineru_caption_without_vision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir,
                "![generic](images/reactor.png)\n",
            )
            asset = images / "reactor.png"
            asset.write_bytes(b"reactor")
            reference = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )[0]
            evidence = {
                "path": str(asset.resolve()),
                "caption": "Figure 1. Temperature profile of the first reactor.",
                "visual_type": "image",
                "page_idx": 0,
                "bbox": [0, 0, 1, 1],
                "source": "content_list",
            }
            record = rename_markdown_assets.AssetRecord(
                path=asset.resolve(),
                sha256=rename_markdown_assets.sha256_file(asset),
                references=[reference],
                evidence=[evidence],
            )

            rename_markdown_assets.propose_names(
                root,
                {asset.resolve(): record},
                {asset.resolve(): [evidence]},
            )

        self.assertIn(
            "fig01-first-reactor-temperature-profile",
            record.proposed_name,
        )
        self.assertEqual(record.reason, "mineru-caption")

    def test_markdown_context_falls_back_from_alt_to_caption_heading_paragraph(
        self,
    ):
        cases = [
            (
                "# Heading\n\nContext paragraph.\n\n"
                "![](images/a.png)\nFigure 2. Caption text.\n",
                ("figure", "Figure 2. Caption text.", "markdown-caption"),
            ),
            (
                "# Heading\n\n![](images/a.png)\n",
                ("figure", "Heading", "markdown-heading"),
            ),
            (
                "Context paragraph.\n\n![](images/a.png)\n",
                ("figure", "Context paragraph.", "markdown-paragraph"),
            ),
            (
                "![](images/a.png)\n",
                ("figure", "asset", "generic-fallback"),
            ),
        ]
        for markdown, expected in cases:
            with self.subTest(expected=expected):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root, images, markdown_path = self.make_markdown_tree(
                        temp_dir, markdown
                    )
                    asset = images / "a.png"
                    asset.write_bytes(b"a")
                    reference = rename_markdown_assets.scan_markdown(
                        markdown_path, root
                    )[0]
                    record = rename_markdown_assets.AssetRecord(
                        path=asset.resolve(),
                        sha256="b" * 64,
                        references=[reference],
                        evidence=[],
                    )

                    selected = rename_markdown_assets.choose_evidence(
                        record, {}
                    )

                self.assertEqual(selected, expected)

    def test_markdown_context_extracts_reference_style_alt_text(self):
        markdown = (
            "# Results\n\n"
            "![Reference reactor profile][reactor]\n\n"
            "[reactor]: images/reactor.png\n"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown_path = self.make_markdown_tree(
                temp_dir, markdown
            )
            (images / "reactor.png").write_bytes(b"reactor")
            reference = rename_markdown_assets.scan_markdown(
                markdown_path, root
            )[0]

            context = rename_markdown_assets.markdown_context(reference)

        self.assertEqual(
            context["alt_text"],
            "Reference reactor profile",
        )

    def test_propose_names_is_stable_shared_and_collision_safe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            docs.mkdir()
            images.mkdir()
            first = images / "one.PNG"
            second = images / "two.png"
            first.write_bytes(b"one")
            second.write_bytes(b"two")
            (docs / "a.md").write_text(
                "![Pressure curve](../images/one.PNG)\n"
                "![Pressure curve](../images/two.png)\n",
                encoding="utf-8",
            )
            (docs / "b.md").write_text(
                "![shared](../images/one.PNG)\n",
                encoding="utf-8",
            )
            _documents, assets, _warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

            first_result = rename_markdown_assets.propose_names(
                root, assets, {}
            )
            first_names = [
                record.proposed_name for record in first_result.values()
            ]
            second_result = rename_markdown_assets.propose_names(
                root, assets, {}
            )

        self.assertEqual(list(first_result), sorted(first_result))
        self.assertEqual(len(first_result[first.resolve()].references), 2)
        self.assertEqual(
            first_names,
            [record.proposed_name for record in second_result.values()],
        )
        self.assertEqual(
            len({name.casefold() for name in first_names}),
            len(first_names),
        )
        self.assertTrue(all("-" + record.sha256[:8] in record.proposed_name
                            for record in first_result.values()))

    def test_propose_names_avoids_existing_case_insensitive_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            docs.mkdir()
            images.mkdir()
            asset = images / "source.png"
            asset.write_bytes(b"source")
            digest = rename_markdown_assets.sha256_file(asset)
            expected = rename_markdown_assets.safe_filename(
                "docs-report-fig01-pressure-curve",
                ".png",
                digest[:8],
            )
            blocker = images / expected.upper()
            blocker.write_bytes(b"blocker")
            (docs / "report.md").write_text(
                "![Figure 1. Pressure curve](../images/source.png)\n",
                encoding="utf-8",
            )
            _documents, assets, _warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

            result = rename_markdown_assets.propose_names(
                root, assets, {}
            )

        self.assertNotEqual(
            result[asset.resolve()].proposed_name.casefold(),
            blocker.name.casefold(),
        )

    def test_collision_suffix_preserves_each_asset_content_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            docs.mkdir()
            images.mkdir()
            first = images / "first.png"
            second = images / "second.png"
            first.write_bytes(b"first-content")
            second.write_bytes(b"second-content")
            (docs / "report.md").write_text(
                "![Figure 1. Pressure curve](../images/first.png)\n"
                "![Figure 1. Pressure curve](../images/second.png)\n",
                encoding="utf-8",
            )
            first_hash = rename_markdown_assets.sha256_file(first)[:8]
            second_hash = rename_markdown_assets.sha256_file(second)[:8]
            for hash8 in (first_hash, second_hash):
                blocker = images / rename_markdown_assets.safe_filename(
                    "docs-report-fig01-pressure-curve",
                    ".png",
                    hash8,
                )
                blocker.write_bytes(b"blocker")
            _documents, assets, _warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

            result = rename_markdown_assets.propose_names(
                root, assets, {}
            )

        first_name = result[first.resolve()].proposed_name
        second_name = result[second.resolve()].proposed_name
        self.assertIn("-" + first_hash + "-", first_name)
        self.assertIn("-" + second_hash + "-", second_name)
        self.assertNotEqual(first_name.casefold(), second_name.casefold())
        self.assertEqual(
            [first_name, second_name],
            [
                result[first.resolve()].proposed_name,
                result[second.resolve()].proposed_name,
            ],
        )

    def test_shared_asset_uses_neutral_slug_not_single_document_stem(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            docs.mkdir()
            images.mkdir()
            shared = images / "shared.png"
            shared.write_bytes(b"shared")
            (docs / "a.md").write_text(
                "![Pressure curve](../images/shared.png)\n",
                encoding="utf-8",
            )
            (docs / "b.md").write_text(
                "![Pressure curve](../images/shared.png)\n",
                encoding="utf-8",
            )
            _documents, assets, _warnings = (
                rename_markdown_assets.build_asset_graph(root)
            )

            result = rename_markdown_assets.propose_names(
                root, assets, {}
            )

        proposed = result[shared.resolve()].proposed_name
        self.assertNotIn("docs-a", proposed)
        self.assertNotIn("docs-b", proposed)
        self.assertIn("shared", proposed)

    def test_create_plan_is_read_only_deterministic_and_has_stable_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            output = root / "plan"
            docs.mkdir()
            images.mkdir()
            asset = images / "reactor.png"
            asset.write_bytes(b"reactor")
            unused = images / "unused.png"
            unused.write_bytes(b"unused")
            markdown = docs / "report.md"
            markdown.write_text(
                "# Results\n\n"
                "![Outlet temperature](../images/reactor.png)\n",
                encoding="utf-8",
            )
            before = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in (asset, unused, markdown)
            }

            first = rename_markdown_assets.create_plan(root, output)
            first_json = (output / "rename-plan.json").read_bytes()
            first_csv = (output / "rename-plan.csv").read_bytes()
            second = rename_markdown_assets.create_plan(root, output)
            second_json = (output / "rename-plan.json").read_bytes()
            second_csv = (output / "rename-plan.csv").read_bytes()
            after = {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in (asset, unused, markdown)
            }

        self.assertEqual(before, after)
        self.assertEqual(first, second)
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_csv, second_csv)
        self.assertTrue(first_csv.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(first["schema"], 1)
        self.assertNotIn("timestamp", first)
        self.assertEqual(len(first["assets"]), 1)
        entry = first["assets"][0]
        self.assertTrue(
            {
                "old_path",
                "new_path",
                "sha256",
                "reason",
                "references",
                "vision_status",
            }.issubset(entry)
        )
        self.assertEqual(entry["old_path"], "images/reactor.png")
        self.assertEqual(entry["vision_status"], "not-needed")
        self.assertTrue(all("\\" not in entry[key]
                            for key in ("old_path", "new_path")))
        self.assertEqual(
            first["summary"],
            {
                "documents": 1,
                "unique_references": 1,
                "eligible_assets": 1,
                "missing_assets": 0,
                "unreferenced_assets": 1,
                "vision_needed_assets": 0,
                "vision_calls": 0,
                "warnings": 1,
            },
        )

    def test_rewrite_markdown_bytes_only_replaces_requested_spans(self):
        source = (
            b'![plot](images/a%20b.png "title")\r\n'
            b"<details>keep</details>\r\n"
            b"[plot]: <images/a%20b.png> 'caption'\r\n"
        )
        first = source.index(b"images/a%20b.png")
        second = source.rindex(b"images/a%20b.png")

        rewritten = rename_markdown_assets.rewrite_markdown_bytes(
            source,
            [
                (first, first + len(b"images/a%20b.png"), b"images/new.png"),
                (second, second + len(b"images/a%20b.png"), b"images/new.png"),
            ],
        )

        self.assertEqual(
            rewritten,
            (
                b'![plot](images/new.png "title")\r\n'
                b"<details>keep</details>\r\n"
                b"[plot]: <images/new.png> 'caption'\r\n"
            ),
        )
        self.assertIn(b'"title"', rewritten)
        self.assertIn(b"<details>keep</details>", rewritten)
        self.assertIn(b"\r\n", rewritten)
        with self.assertRaises(ValueError):
            rename_markdown_assets.rewrite_markdown_bytes(
                source,
                [(0, 5, b"a"), (4, 8, b"b")],
            )

    def test_apply_plan_renames_assets_rewrites_references_and_commits(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            output = root / "plan"
            docs.mkdir()
            images.mkdir()
            space_asset = images / "a b.png"
            raw_asset = images / "\u56fe.png"
            space_asset.write_bytes(b"space-asset")
            raw_asset.write_bytes(b"raw-asset")
            markdown = docs / "report.md"
            markdown.write_text(
                "# Report\r\n"
                '![percent](../images/a%20b.png "title")\r\n'
                "![raw](../images/\u56fe.png)\r\n"
                "![again][plot]\r\n"
                "[plot]: <../images/a%20b.png> 'caption'\r\n"
                "<details>unchanged</details>\r\n"
                '<img alt="chart" src="../images/\u56fe.png?width=2#preview">\r\n',
                encoding="utf-8",
                newline="",
            )
            plan = rename_markdown_assets.create_plan(root, output)
            for entry in plan["assets"]:
                if entry["old_path"] == "images/a b.png":
                    entry["new_path"] = "images/renamed space \u56fe.png"
                elif entry["old_path"] == "images/\u56fe.png":
                    entry["new_path"] = "images/\u539f\u59cb\u540d\u79f0.png"
            plan_path = output / "rename-plan.json"
            self.write_json(plan_path, plan)
            original_markdown = markdown.read_bytes()

            result = rename_markdown_assets.apply_plan(plan_path)

            journal = json.loads(
                Path(result["transaction_path"]).read_text(encoding="utf-8")
            )
            rewritten = markdown.read_text(encoding="utf-8", newline="")
            validation_errors = rename_markdown_assets.validate_plan(plan_path)
            space_exists = space_asset.exists()
            raw_exists = raw_asset.exists()
            backup_ops = [
                operation
                for operation in journal["operations"]
                if operation["op"] == "backup-markdown"
            ]
            backup_bytes = Path(backup_ops[0]["backup"]).read_bytes()

        self.assertFalse(space_exists)
        self.assertFalse(raw_exists)
        self.assertEqual(journal["state"], "committed")
        self.assertEqual(validation_errors, [])
        self.assertEqual(backup_bytes, original_markdown)
        self.assertIn("../images/renamed%20space%20%E5%9B%BE.png", rewritten)
        self.assertIn(
            "<../images/renamed%20space%20%E5%9B%BE.png> 'caption'",
            rewritten,
        )
        self.assertIn("../images/\u539f\u59cb\u540d\u79f0.png)", rewritten)
        self.assertIn(
            'src="../images/\u539f\u59cb\u540d\u79f0.png?width=2#preview"',
            rewritten,
        )
        self.assertIn('"title"', rewritten)
        self.assertIn("<details>unchanged</details>", rewritten)
        self.assertIn("\r\n", rewritten)

    def test_apply_plan_rejects_changed_markdown_before_moving_asset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, markdown = self.make_markdown_tree(
                temp_dir,
                "![plot](images/a.png)\n",
            )
            asset = images / "a.png"
            asset.write_bytes(b"asset")
            output = root / "plan"
            rename_markdown_assets.create_plan(root, output)
            plan_path = output / "rename-plan.json"
            markdown.write_text(
                "![plot](images/changed.png)\n",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                rename_markdown_assets.apply_plan(plan_path)

            self.assertTrue(asset.exists())
            self.assertFalse(any(images.glob("*changed*")))

    def test_preflight_plan_rejects_critical_plan_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, _markdown = self.make_markdown_tree(
                temp_dir,
                "![plot](images/a.png)\n",
            )
            asset = images / "a.png"
            asset.write_bytes(b"asset")
            output = root / "plan"
            clean_plan = rename_markdown_assets.create_plan(root, output)
            plan_path = output / "rename-plan.json"

            cases = []
            bad_schema = dict(clean_plan)
            bad_schema["schema"] = 99
            cases.append(("schema", bad_schema))

            escaped = json.loads(json.dumps(clean_plan))
            escaped["assets"][0]["new_path"] = "../escape.png"
            cases.append(("root", escaped))

            collision = json.loads(json.dumps(clean_plan))
            target = root / collision["assets"][0]["new_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"occupied")
            cases.append(("collision", collision))

            for label, plan in cases:
                with self.subTest(label=label):
                    self.write_json(plan_path, plan)
                    with self.assertRaises(RuntimeError):
                        rename_markdown_assets.preflight_plan(plan, plan_path)
                    if label == "collision":
                        target.unlink()

            hash_changed = json.loads(json.dumps(clean_plan))
            asset.write_bytes(b"changed")
            self.write_json(plan_path, hash_changed)
            with self.assertRaises(RuntimeError):
                rename_markdown_assets.preflight_plan(hash_changed, plan_path)
            asset.write_bytes(b"asset")

            clean_copy = json.loads(json.dumps(clean_plan))
            asset.unlink()
            self.write_json(plan_path, clean_copy)
            with self.assertRaises(RuntimeError):
                rename_markdown_assets.preflight_plan(clean_copy, plan_path)

    def test_create_plan_uses_injected_vision_only_for_generic_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            docs = root / "docs"
            images = root / "images"
            output = root / "plan"
            docs.mkdir()
            images.mkdir()
            generic = images / "generic.png"
            context = images / "context.png"
            mineru = images / "mineru.png"
            generic.write_bytes(b"generic")
            context.write_bytes(b"context")
            mineru.write_bytes(b"mineru")
            (docs / "generic.md").write_text(
                "![](../images/generic.png)\n",
                encoding="utf-8",
            )
            (docs / "context.md").write_text(
                "![Outlet temperature trend](../images/context.png)\n",
                encoding="utf-8",
            )
            (docs / "mineru.md").write_text(
                "![](../images/mineru.png)\n",
                encoding="utf-8",
            )
            self.write_json(
                root / "content_list.json",
                [
                    {
                        "img_path": "images/mineru.png",
                        "caption": "Figure 9. Reactor pressure profile.",
                    }
                ],
            )
            calls = []

            def fake_vision(path, context_data, config):
                calls.append((path.name, context_data, config))
                return {
                    "description": "distillation column schematic",
                    "keywords": ["distillation", "column", "schematic"],
                    "confidence": 0.93,
                }

            plan = rename_markdown_assets.create_plan(
                root,
                output,
                use_vision=True,
                vision_analyzer=fake_vision,
            )

        self.assertEqual([name for name, _context, _config in calls],
                         ["generic.png"])
        by_old_path = {
            entry["old_path"]: entry
            for entry in plan["assets"]
        }
        generic_entry = by_old_path["images/generic.png"]
        self.assertEqual(generic_entry["vision_status"], "used")
        self.assertIn(
            "distillation-column-schematic",
            generic_entry["new_path"],
        )
        self.assertEqual(
            by_old_path["images/context.png"]["vision_status"],
            "not-needed",
        )
        self.assertEqual(
            by_old_path["images/mineru.png"]["vision_status"],
            "not-needed",
        )
        self.assertEqual(plan["summary"]["vision_needed_assets"], 1)
        self.assertEqual(plan["summary"]["vision_calls"], 1)
        self.assertEqual(
            plan["metadata"]["vision"]["prompt_version"],
            rename_markdown_assets.PROMPT_VERSION,
        )
        self.assertNotIn(
            "api_key",
            json.dumps(plan["metadata"], sort_keys=True).casefold(),
        )

    def test_create_plan_rejects_low_confidence_and_generic_vision(self):
        cases = [
            (
                {
                    "description": "packed bed reactor cross section",
                    "keywords": ["reactor"],
                    "confidence": 0.49,
                },
                "rejected",
            ),
            (
                {
                    "description": "image",
                    "keywords": ["image"],
                    "confidence": 0.98,
                },
                "rejected",
            ),
        ]
        for response, expected_status in cases:
            with self.subTest(response=response):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root, images, _markdown_path = self.make_markdown_tree(
                        temp_dir,
                        "![](images/a.png)\n",
                    )
                    asset = images / "a.png"
                    asset.write_bytes(b"generic")
                    output = root / "plan"

                    plan = rename_markdown_assets.create_plan(
                        root,
                        output,
                        use_vision=True,
                        vision_analyzer=lambda _path, _context, _config: (
                            response
                        ),
                    )

                entry = plan["assets"][0]
                self.assertEqual(entry["vision_status"], expected_status)
                self.assertEqual(entry["reason"], "generic-fallback")
                self.assertIn("-" + entry["sha256"][:8], entry["new_path"])
                self.assertIn("asset", entry["new_path"])

    def test_create_plan_marks_vision_failure_and_keeps_stable_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, _markdown_path = self.make_markdown_tree(
                temp_dir,
                "![](images/a.png)\n",
            )
            asset = images / "a.png"
            asset.write_bytes(b"generic")
            output = root / "plan"

            def unavailable(_path, _context, _config):
                raise RuntimeError("provider unavailable")

            first = rename_markdown_assets.create_plan(
                root,
                output,
                use_vision=True,
                vision_analyzer=unavailable,
            )
            second = rename_markdown_assets.create_plan(
                root,
                output,
                use_vision=True,
                vision_analyzer=unavailable,
            )

        self.assertEqual(first, second)
        entry = first["assets"][0]
        self.assertEqual(entry["vision_status"], "failed")
        self.assertEqual(entry["reason"], "generic-fallback")
        self.assertIn("-" + entry["sha256"][:8], entry["new_path"])

    def test_vision_cache_key_is_deterministic_and_includes_inputs(self):
        first = rename_markdown_assets.vision_cache_key(
            "a" * 64,
            "gpt-4.1-mini",
            "semantic-asset-name-v1",
        )
        second = rename_markdown_assets.vision_cache_key(
            "a" * 64,
            "gpt-4.1-mini",
            "semantic-asset-name-v1",
        )
        changed = rename_markdown_assets.vision_cache_key(
            "b" * 64,
            "gpt-4.1-mini",
            "semantic-asset-name-v1",
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertIn("a" * 64, first)
        self.assertIn("gpt-4.1-mini", first)
        self.assertIn("semantic-asset-name-v1", first)

    def test_vision_cache_is_written_without_key_and_reused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, _markdown_path = self.make_markdown_tree(
                temp_dir,
                "![](images/a.png)\n",
            )
            asset = images / "a.png"
            asset.write_bytes(b"generic")
            output = root / "plan"
            calls = []

            def fake_vision(path, _context, _config):
                calls.append(path.name)
                return {
                    "description": "absorber tower diagram",
                    "keywords": ["absorber", "tower"],
                    "confidence": 0.91,
                }

            with patch.dict(
                "os.environ",
                {
                    "MARKITDOWN_OCR_API_KEY": "secret-test-key",
                    "MARKITDOWN_OCR_BASE_URL": "https://api.ikuncode.cc/v1",
                    "MARKITDOWN_OCR_MODEL": "vision-test-model",
                },
            ):
                first = rename_markdown_assets.create_plan(
                    root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
                second = rename_markdown_assets.create_plan(
                    root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
            cache_text = (output / ".asset-name-cache.json").read_text(
                encoding="utf-8"
            )

        self.assertEqual(calls, ["a.png"])
        self.assertIn("absorber-tower-diagram", first["assets"][0]["new_path"])
        self.assertEqual(first["assets"][0]["new_path"],
                         second["assets"][0]["new_path"])
        self.assertEqual(first["assets"][0]["vision_status"], "used")
        self.assertEqual(second["assets"][0]["vision_status"], "used")
        self.assertEqual(first["summary"]["vision_calls"], 1)
        self.assertEqual(second["summary"]["vision_calls"], 0)
        self.assertNotIn("secret-test-key", cache_text)
        self.assertEqual(
            first["metadata"]["vision"]["base_url_classification"],
            "third-party OpenAI-compatible relay",
        )
        self.assertEqual(
            first["metadata"]["vision"]["model"],
            "vision-test-model",
        )

    def test_vision_cache_key_includes_request_context_internally(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            output = workspace / "plan"
            calls = []

            def make_tree(name):
                root = workspace / name
                docs = root / "docs"
                images = root / "images"
                docs.mkdir(parents=True)
                images.mkdir()
                asset = images / "shared.png"
                asset.write_bytes(b"same-bytes")
                (docs / f"{name}.md").write_text(
                    "![](../images/shared.png)\n",
                    encoding="utf-8",
                )
                return root

            first_root = make_tree("first")
            second_root = make_tree("second")

            def fake_vision(path, context_data, _config):
                calls.append(context_data["references"][0]["document"])
                return {
                    "description": "context specific schematic",
                    "keywords": ["context", "schematic"],
                    "confidence": 0.92,
                }

            with patch.dict(
                "os.environ",
                {
                    "MARKITDOWN_OCR_API_KEY": "secret-test-key",
                    "MARKITDOWN_OCR_MODEL": "vision-test-model",
                },
            ):
                first = rename_markdown_assets.create_plan(
                    first_root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
                second = rename_markdown_assets.create_plan(
                    second_root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
                third = rename_markdown_assets.create_plan(
                    second_root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
            cache = json.loads(
                (output / ".asset-name-cache.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(calls, ["docs/first.md", "docs/second.md"])
        self.assertEqual(first["summary"]["vision_calls"], 1)
        self.assertEqual(second["summary"]["vision_calls"], 1)
        self.assertEqual(third["summary"]["vision_calls"], 0)
        self.assertEqual(len(cache["entries"]), 2)
        self.assertNotIn("secret-test-key", json.dumps(cache, sort_keys=True))

    def test_analyze_image_with_vision_sends_bounded_openai_request(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
                self.read_size = None

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def read(self, size=-1):
                self.read_size = size
                return self.payload

        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "diagram.png"
            image.write_bytes(b"png")
            body = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "description": "heat exchanger diagram",
                                    "keywords": ["heat", "exchanger"],
                                    "confidence": 0.94,
                                }
                            )
                        }
                    }
                ]
            }
            response = FakeResponse(json.dumps(body).encode("utf-8"))
            captured = {}

            def fake_urlopen(request, timeout):
                captured["timeout"] = timeout
                captured["authorization"] = request.get_header(
                    "Authorization"
                )
                captured["content_type"] = request.get_header("Content-type")
                captured["payload"] = json.loads(
                    request.data.decode("utf-8")
                )
                return response

            with patch.object(
                rename_markdown_assets.urllib_request,
                "urlopen",
                side_effect=fake_urlopen,
            ):
                result = rename_markdown_assets.analyze_image_with_vision(
                    image,
                    {"nearby": "context"},
                    {
                        "api_key": "secret-test-key",
                        "base_url": "https://example.test/v1",
                        "model": "vision-model",
                    },
                )

        self.assertEqual(result["description"], "heat exchanger diagram")
        self.assertEqual(captured["timeout"], 60)
        self.assertEqual(captured["authorization"], "Bearer secret-test-key")
        self.assertEqual(captured["content_type"], "application/json")
        self.assertEqual(captured["payload"]["model"], "vision-model")
        self.assertEqual(
            response.read_size,
            rename_markdown_assets.MAX_VISION_RESPONSE_BYTES + 1,
        )

    def test_analyze_image_with_vision_raises_controlled_errors(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, _exc_type, _exc, _traceback):
                return False

            def read(self, size=-1):
                return self.payload

        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "diagram.png"
            image.write_bytes(b"png")
            config = {
                "api_key": "secret-test-key",
                "base_url": "https://example.test/v1",
                "model": "vision-model",
            }
            cases = [
                b"not-json",
                json.dumps([]).encode("utf-8"),
                json.dumps({"choices": []}).encode("utf-8"),
                json.dumps(
                    {"choices": [{"message": {"content": "not-json"}}]}
                ).encode("utf-8"),
                json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(["not-object"])
                                }
                            }
                        ]
                    }
                ).encode("utf-8"),
                b"\xff",
                b"{" + (
                    b" " * rename_markdown_assets.MAX_VISION_RESPONSE_BYTES
                ),
            ]
            for payload in cases:
                with self.subTest(payload=payload[:20]):
                    with patch.object(
                        rename_markdown_assets.urllib_request,
                        "urlopen",
                        return_value=FakeResponse(payload),
                    ):
                        with self.assertRaises(
                            rename_markdown_assets.VisionAnalysisError
                        ) as raised:
                            rename_markdown_assets.analyze_image_with_vision(
                                image,
                                {},
                                config,
                            )
                    self.assertNotIn("secret-test-key", str(raised.exception))

            with patch.object(
                rename_markdown_assets.urllib_request,
                "urlopen",
                side_effect=OSError("secret-test-key provider down"),
            ):
                with self.assertRaises(
                    rename_markdown_assets.VisionAnalysisError
                ) as raised:
                    rename_markdown_assets.analyze_image_with_vision(
                        image,
                        {},
                        config,
                    )
            self.assertNotIn("secret-test-key", str(raised.exception))

    def test_analyze_image_with_vision_rejects_oversized_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "too-large.png"
            image.write_bytes(b"large")
            with patch.object(
                rename_markdown_assets,
                "MAX_VISION_IMAGE_BYTES",
                4,
            ):
                with self.assertRaises(
                    rename_markdown_assets.VisionAnalysisError
                ):
                    rename_markdown_assets.analyze_image_with_vision(
                        image,
                        {},
                        {
                            "api_key": "secret-test-key",
                            "base_url": "https://example.test/v1",
                            "model": "vision-model",
                        },
                    )

    def test_vision_failures_do_not_write_api_key_to_plan_or_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, _markdown_path = self.make_markdown_tree(
                temp_dir,
                "![](images/a.png)\n",
            )
            (images / "a.png").write_bytes(b"generic")
            output = root / "plan"

            def fake_vision(_path, _context, _config):
                raise rename_markdown_assets.VisionAnalysisError(
                    "secret-test-key provider unavailable"
                )

            with patch.dict(
                "os.environ",
                {"MARKITDOWN_OCR_API_KEY": "secret-test-key"},
            ):
                plan = rename_markdown_assets.create_plan(
                    root,
                    output,
                    use_vision=True,
                    vision_analyzer=fake_vision,
                )
            plan_text = (output / "rename-plan.json").read_text(
                encoding="utf-8"
            )
            cache_text = (output / ".asset-name-cache.json").read_text(
                encoding="utf-8"
            )

        self.assertEqual(plan["assets"][0]["vision_status"], "failed")
        self.assertNotIn("secret-test-key", plan_text)
        self.assertNotIn("secret-test-key", cache_text)

    def test_vision_cache_write_prunes_invalid_nested_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir)
            rename_markdown_assets._write_vision_cache(
                output,
                {
                    "schema": 1,
                    "entries": {
                        "valid": {
                            "prompt_version": "semantic-asset-name-v1",
                            "model": "vision-model",
                            "sha256": "a" * 64,
                            "context_digest": "b" * 64,
                            "result": {
                                "description": "valid diagram",
                                "keywords": ["valid"],
                                "confidence": 0.9,
                            },
                        },
                        "not-a-dict": "bad",
                        "bad-result": {
                            "result": {
                                "description": "",
                                "keywords": [],
                                "confidence": 0.9,
                            }
                        },
                    },
                },
            )
            cache = json.loads(
                (output / ".asset-name-cache.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(list(cache["entries"]), ["valid"])

    def test_create_plan_without_vision_does_not_load_vision_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root, images, _markdown_path = self.make_markdown_tree(
                temp_dir,
                "![](images/a.png)\n",
            )
            (images / "a.png").write_bytes(b"generic")
            with patch.object(
                rename_markdown_assets,
                "load_vision_config",
                side_effect=AssertionError("vision config loaded"),
            ):
                plan = rename_markdown_assets.create_plan(
                    root,
                    root / "plan",
                )

        self.assertNotIn("metadata", plan)


if __name__ == "__main__":
    unittest.main()
