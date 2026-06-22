import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "rename-markdown-assets.py"
SPEC = importlib.util.spec_from_file_location("rename_markdown_assets", SCRIPT_PATH)
rename_markdown_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rename_markdown_assets)

SOURCE = Path(
    os.environ.get(
        "MARKDOWN_ASSET_REAL_FIXTURE",
        (
            r"F:\化工设计比赛\华南赛区-华南农业大学-凭苯事吃饭"
            r"\4-动力学来源说明\参考文献\markdown"
        ),
    )
)


def snapshot_tree(root):
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


@unittest.skipUnless(SOURCE.is_dir(), "real fixture not found: {}".format(SOURCE))
class RealMinerUFixtureTests(unittest.TestCase):
    def test_plan_apply_validate_and_rollback_on_temporary_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            copied = temp_root / "markdown"
            shutil.copytree(SOURCE, copied)
            before = snapshot_tree(copied)

            plan = rename_markdown_assets.create_plan(
                copied,
                temp_root / "plan",
                use_vision=False,
            )
            plan_path = temp_root / "plan" / "rename-plan.json"
            matching_names = [
                entry["new_path"]
                for entry in plan["assets"]
                if "fig01-first-reactor-temperature-profile" in entry["new_path"]
            ]
            matching_entries = [
                entry
                for entry in plan["assets"]
                if "fig01-first-reactor-temperature-profile" in entry["new_path"]
            ]

            self.assertEqual(plan["summary"]["documents"], 4)
            self.assertEqual(plan["summary"]["eligible_assets"], 47)
            self.assertEqual(plan["summary"]["unreferenced_assets"], 94)
            self.assertTrue(matching_names, json.dumps(
                plan["assets"],
                ensure_ascii=False,
            ))
            self.assertEqual(matching_entries[0]["vision_status"], "not-needed")

            result = rename_markdown_assets.apply_plan(plan_path)
            self.assertEqual(rename_markdown_assets.validate_plan(plan_path), [])
            self.assertEqual(
                rename_markdown_assets.rollback_transaction(
                    Path(result["transaction_path"])
                ),
                [],
            )
            self.assertEqual(snapshot_tree(copied), before)


if __name__ == "__main__":
    unittest.main()
