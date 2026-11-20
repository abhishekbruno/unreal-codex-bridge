import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import configure as c


class ConfigurationTests(unittest.TestCase):
    def test_public_port_override_rejected_before_configuration(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'Engine.ini'
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress=any)\n')
            with self.assertRaisesRegex(ValueError,'ListenerOverrides'):
                c.guard_listener_overrides([path],8000)
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="127.0.0.1")\n')
            c.guard_listener_overrides([path],8000)

    def test_plugins_preserve_other_entries_and_fields(self):
        data = {'FileVersion':3,'Plugins':[{'Name':'Other','Enabled':False,'Custom':42}]}
        result = json.loads(c.plugin_content(json.dumps(data)))
        self.assertEqual(result['Plugins'][0], data['Plugins'][0])
        self.assertTrue(all(next(x for x in result['Plugins'] if x['Name']==n)['Enabled'] for n in ('ModelContextProtocol','AllToolsets')))
        self.assertEqual(c.plugin_content(json.dumps(result)), json.dumps(result))

    def test_existing_codex_is_byte_preserved(self):
        original = '# comment\n[mcp_servers."engine"]\nurl="http://localhost:8000/mcp"\n\n[mcp_servers.other]\nurl="https://example.com"\n'
        self.assertEqual(c.codex_content(original,'http://127.0.0.1:8000/mcp'), original)

    def test_new_registration_preserves_other_servers(self):
        original = '[mcp_servers.other]\ncommand="other"\n'
        result = c.codex_content(original,'http://127.0.0.1:8000/mcp')
        self.assertTrue(result.startswith(original))
        self.assertEqual(tomllib.loads(result)['mcp_servers']['other'], {'command':'other'})

    def test_duplicates_and_conflicts_are_refused(self):
        for text in ('[mcp_servers.a]\nurl="http://localhost:8000/mcp"\n[mcp_servers.b]\nurl="http://127.0.0.1:8000/mcp"',
                     '[mcp_servers.unreal-mcp]\nurl="http://127.0.0.1:9000/mcp"'):
            with self.assertRaises(ValueError): c.codex_content(text,'http://127.0.0.1:8000/mcp')

    def test_backup_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'file.ini'; p.write_text('original')
            c.write_backed_up(p,'changed')
            backups=list(p.parent.glob('file.ini.backup-*'))
            self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_text(),'original')
            c.write_backed_up(p,'changed')
            self.assertEqual(len(list(p.parent.glob('file.ini.backup-*'))),1)

    def test_ini_preserves_other_sections(self):
        before='[Other]\nKey=Value\n[Target]\nX=old\n[After]\nZ=1\n'
        after=c.ini_content(before,'Target',{'X':'new','Y':'2'})
        self.assertIn('[Other]\nKey=Value\n',after)
        self.assertIn('[After]\nZ=1\n',after)
        self.assertEqual(c.ini_content(after,'Target',{'X':'new','Y':'2'}),after)


if __name__=='__main__': unittest.main()
