import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "rename-markdown-assets.py"
SPEC = importlib.util.spec_from_file_location("rename_markdown_assets", SCRIPT_PATH)
rename_markdown_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rename_markdown_assets)


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

    def test_metadata_skips_bad_paths_and_normalizes_malformed_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image = root / "images" / "valid.png"
            image.parent.mkdir()
            image.write_bytes(b"valid")
            self.write_json(
                root / "content_list.json",
                [
                    {"img_path": ""},
                    {"img_path": "images/bad\u0000.png"},
                    {"img_path": "images/not-supported.txt"},
                    {
                        "img_path": "images/valid.png",
                        "caption": {"bad": "shape"},
                        "page_idx": -1,
                        "bbox": [1, float("nan"), 3, 4],
                        "type": ["bad-shape"],
                    },
                    {
                        "img_path": "images/valid.png",
                        "caption": [" First ", 7, "", "Second"],
                        "page_idx": 4.0,
                        "bbox": [1, 2, 3, 4],
                        "type": " image ",
                    },
                ],
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
                },
                {
                    "path": str(image.resolve()),
                    "caption": "First Second",
                    "visual_type": "image",
                    "page_idx": 4,
                    "bbox": [1, 2, 3, 4],
                    "source": "content_list",
                },
            ],
        )

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

        with (
            patch.object(
                Path,
                "rglob",
                autospec=True,
                return_value=[outside_link, alias, lower],
            ),
            patch.object(Path, "is_file", autospec=True, return_value=True),
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=resolve_candidates,
            ),
        ):
            documents = rename_markdown_assets.iter_markdown_files(root)

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


if __name__ == "__main__":
    unittest.main()
