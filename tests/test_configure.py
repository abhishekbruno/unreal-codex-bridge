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

    def test_listener_overrides_comprehensive_security(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'Engine.ini'

            # 1. Valid IPv6 loopback
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="::1")\n')
            c.guard_listener_overrides([path], 8000)

            # 2. Valid localhost string and IPv4 loopback variation
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress=localhost)\n')
            c.guard_listener_overrides([path], 8000)
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="127.0.0.8")\n')
            c.guard_listener_overrides([path], 8000)

            # 3. Wildcard IPv4 (0.0.0.0) and IPv6 (::)
            for wild in ('0.0.0.0', '::', '*', '""'):
                path.write_text(f'[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress={wild})\n')
                with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                    c.guard_listener_overrides([path], 8000)

            # 4. Public IPv4 (LAN and WAN)
            for pub in ('192.168.1.50', '10.0.0.1', '8.8.8.8'):
                path.write_text(f'[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="{pub}")\n')
                with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                    c.guard_listener_overrides([path], 8000)

            # 5. Non-loopback IPv6
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="2001:db8::1")\n')
            with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                c.guard_listener_overrides([path], 8000)

            # 6. Malformed address
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000,BindAddress="not_a_valid_ip")\n')
            with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                c.guard_listener_overrides([path], 8000)

            # 7. Missing BindAddress parameter
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=8000)\n')
            with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                c.guard_listener_overrides([path], 8000)

            # 8. Malformed port
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=abc,BindAddress="127.0.0.1")\n')
            with self.assertRaisesRegex(ValueError, 'ListenerOverrides'):
                c.guard_listener_overrides([path], 8000)

            # 9. Conflicting overrides on same port
            conflicting = ('[HTTPServer.Listeners]\n'
                           '+ListenerOverrides=(Port=8000,BindAddress="127.0.0.1")\n'
                           '+ListenerOverrides=(Port=8000,BindAddress="127.0.0.2")\n')
            path.write_text(conflicting)
            with self.assertRaisesRegex(ValueError, 'Conflicting ListenerOverrides'):
                c.guard_listener_overrides([path], 8000)

            # 10. Overrides on different port are ignored
            path.write_text('[HTTPServer.Listeners]\n+ListenerOverrides=(Port=9000,BindAddress="192.168.1.1")\n')
            c.guard_listener_overrides([path], 8000)

            # 11. Unsafe DefaultBindAddress
            path.write_text('[HTTPServer.Listeners]\nDefaultBindAddress=0.0.0.0\n')
            with self.assertRaisesRegex(ValueError, 'DefaultBindAddress'):
                c.guard_listener_overrides([path], 8000)

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
