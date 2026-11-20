import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("unreal_codex_installer", PACKAGE_ROOT / "scripts" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.project = self.root / "MyGame.uproject"
        self.project.write_text(json.dumps({"FileVersion": 3, "Plugins": [{"Name": "MyPlugin", "Enabled": True}]}), encoding="utf-8")

    def install(self, port=8000):
        installer.enable_project_plugins(self.project)
        installer.enable_autostart(self.root, port)
        installer.install_plugin_files(self.root, port)
        name = installer.merge_marketplace(self.root)
        installer.merge_codex_config(self.root, port, name)
        installer.merge_agent_guidance(self.root)

    def test_project_plugins_backup_and_idempotence(self):
        self.install()
        source = json.loads(self.project.read_text(encoding="utf-8"))
        enabled = {p["Name"] for p in source["Plugins"] if p.get("Enabled")}
        self.assertTrue({"ModelContextProtocol", "AllToolsets", "MyPlugin"} <= enabled)
        self.assertEqual(len(list(self.root.glob("MyGame.uproject.backup-*"))), 1)
        self.install()
        self.assertEqual(len(list(self.root.glob("MyGame.uproject.backup-*"))), 1)
        self.assertEqual((self.root / "AGENTS.md").read_text().count(installer.START_MARKER), 1)
        content = (self.root / ".codex/config.toml").read_text()
        self.assertEqual(content.count("[mcp_servers.unreal-mcp]"), 1)
        self.assertEqual(content.count('[plugins."unreal-codex@unreal-local"]'), 1)
        market = json.loads((self.root / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(len(market["plugins"]), 1)

    def test_existing_config_and_marketplace_preserved(self):
        (self.root / ".codex").mkdir()
        (self.root / ".codex/config.toml").write_text('[mcp_servers.context7]\nurl = "https://example.com/mcp"\n\n[mcp_servers.unreal-mcp]\nurl = "http://127.0.0.1:9999/mcp"\n')
        (self.root / ".agents/plugins").mkdir(parents=True)
        (self.root / ".agents/plugins/marketplace.json").write_text(json.dumps({"name": "my-tools", "plugins": [{"name": "other-plugin", "source": "./somewhere"}]}))
        (self.root / "AGENTS.md").write_text("Existing project guidance.\n")
        self.install(8100)
        cfg = (self.root / ".codex/config.toml").read_text()
        self.assertIn('https://example.com/mcp', cfg)
        self.assertIn('http://127.0.0.1:8100/mcp', cfg)
        self.assertNotIn(':9999/', cfg)
        self.assertIn('[plugins."unreal-codex@my-tools"]', cfg)
        market = json.loads((self.root / ".agents/plugins/marketplace.json").read_text())
        self.assertEqual(len(market["plugins"]), 2)
        self.assertTrue((self.root / "AGENTS.md").read_text().startswith("Existing project guidance."))
        mcp = json.loads((self.root / ".codex-plugins/unreal-codex/mcp.json").read_text())
        self.assertEqual(mcp["mcpServers"]["unreal-mcp"]["url"], "http://127.0.0.1:8100/mcp")

    def test_autostart_updates_existing_section(self):
        ini = self.root / "Saved/Config/WindowsEditor/EditorPerProjectUserSettings.ini"
        ini.parent.mkdir(parents=True)
        ini.write_text("[Other]\nFoo=Bar\n[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]\nbAutoStartServer=False\nServerPortNumber=9900\n[After]\nBaz=Qux\n")
        installer.enable_autostart(self.root, 8000)
        content = ini.read_text()
        self.assertIn("[Other]\nFoo=Bar", content)
        self.assertIn("[After]\nBaz=Qux", content)
        self.assertIn("bAutoStartServer=True", content)
        self.assertIn("ServerPortNumber=8000", content)
        installer.enable_autostart(self.root, 8000)
        self.assertEqual(ini.read_text(), content)

    def test_mcp_skill_frontmatter(self):
        skill = (PACKAGE_ROOT / "skills/unreal-mcp/SKILL.md").read_text()
        self.assertTrue(skill.startswith("---\nname: unreal-mcp\n"))

if __name__ == '__main__':
    unittest.main()
