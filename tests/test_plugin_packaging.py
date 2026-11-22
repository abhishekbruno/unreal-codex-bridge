"""Unit tests for Codex plugin manifest, marketplace catalog, and skill packaging."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PluginPackagingTests(unittest.TestCase):
    def test_plugin_json_schema(self):
        manifest_path = ROOT / ".codex-plugin/plugin.json"
        self.assertTrue(manifest_path.is_file(), f"Missing plugin.json at {manifest_path}")

        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "unreal-codex-bridge")
        self.assertIn("version", data)
        self.assertIn("description", data)
        self.assertEqual(data.get("skills"), "./skills/")
        self.assertEqual(data.get("mcpServers"), "./.mcp.json")

        interface = data.get("interface", {})
        self.assertIn("displayName", interface)
        self.assertIn("shortDescription", interface)
        self.assertEqual(interface.get("category"), "Developer Tools")
        self.assertIn("Interactive", interface.get("capabilities", []))

    def test_marketplace_json_schema(self):
        marketplace_path = ROOT / ".agents/plugins/marketplace.json"
        self.assertTrue(marketplace_path.is_file(), f"Missing marketplace.json at {marketplace_path}")

        data = json.loads(marketplace_path.read_text(encoding="utf-8"))
        self.assertEqual(data.get("name"), "unreal-local")
        self.assertIsInstance(data.get("plugins"), list)
        self.assertEqual(len(data["plugins"]), 1)

        plugin_entry = data["plugins"][0]
        self.assertEqual(plugin_entry.get("name"), "unreal-codex-bridge")
        self.assertEqual(plugin_entry.get("category"), "Developer Tools")
        self.assertEqual(plugin_entry.get("policy", {}).get("installation"), "AVAILABLE")

    def test_mcp_json_schema(self):
        mcp_path = ROOT / ".mcp.json"
        self.assertTrue(mcp_path.is_file(), f"Missing .mcp.json at {mcp_path}")

        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        self.assertIn("unreal-mcp", servers)

        unreal_cfg = servers["unreal-mcp"]
        self.assertEqual(unreal_cfg.get("type"), "http")
        self.assertTrue(unreal_cfg.get("url", "").startswith("http://127.0.0.1:"))
        self.assertTrue(unreal_cfg.get("url", "").endswith("/mcp"))

    def test_all_skills_have_valid_frontmatter(self):
        skills_dir = ROOT / "skills"
        self.assertTrue(skills_dir.is_dir())

        skill_files = list(skills_dir.glob("*/SKILL.md"))
        self.assertTrue(len(skill_files) >= 5, f"Expected at least 5 skills, found {len(skill_files)}")

        skill_names = set()
        for sf in skill_files:
            text = sf.read_text(encoding="utf-8")
            match = re.match(r"^---\r?\n(.*?)\r?\n---", text, re.DOTALL)
            self.assertIsNotNone(match, f"Skill {sf} missing YAML frontmatter")

            frontmatter = match.group(1)
            name_m = re.search(r"^name:\s*([a-zA-Z0-9_\-]+)", frontmatter, re.M)
            desc_m = re.search(r"^description:\s*(.+)", frontmatter, re.M)

            self.assertIsNotNone(name_m, f"Skill {sf} missing name")
            self.assertIsNotNone(desc_m, f"Skill {sf} missing description")

            name = name_m.group(1)
            self.assertNotIn(name, skill_names, f"Duplicate skill name: {name}")
            skill_names.add(name)

        expected_skills = {"unreal-mcp", "create-toolset", "unreal-skill", "unreal-game", "unreal-playtest"}
        self.assertTrue(expected_skills.issubset(skill_names), f"Missing skills: {expected_skills - skill_names}")


if __name__ == "__main__":
    unittest.main()

