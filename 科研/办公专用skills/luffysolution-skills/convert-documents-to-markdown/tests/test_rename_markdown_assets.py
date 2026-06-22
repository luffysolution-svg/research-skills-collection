import importlib.util
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


if __name__ == "__main__":
    unittest.main()
