import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import bridge_mcp as m


class ProtocolTests(unittest.TestCase):
    def test_reject_nonlocal_urls(self):
        for url in ('http://0.0.0.0:8000/mcp', 'https://example.com/mcp',
                    'http://127.0.0.1:8000/mcp?secret=x', 'http://u:p@localhost/mcp'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.validate_endpoint(url)

    def test_accept_loopback(self):
        for url in ('http://127.0.0.1:8000/mcp', 'http://localhost:8100/mcp', 'http://[::1]:8000/mcp'):
            self.assertEqual(m.validate_endpoint(url), url)

    def test_sse_matching_response(self):
        stream = io.BytesIO(b': ping\n\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\ndata: {"jsonrpc":"2.0","id":7,"result":{"tools":[]}}\n\n')
        self.assertEqual(m.read_response(stream, 'text/event-stream', 7), {'tools': []})

    def test_rpc_error_not_success(self):
        stream = io.BytesIO(json.dumps({'jsonrpc':'2.0','id':1,'error':{'code':-32601,'message':'Unknown method'}}).encode())
        with self.assertRaisesRegex(m.MCPError, 'Unknown method'):
            m.read_response(stream, 'application/json', 1)

    def test_wrong_response_id_rejected(self):
        with self.assertRaises(m.MCPError):
            m.read_response(io.BytesIO(b'{"jsonrpc":"2.0","id":2,"result":{}}'), 'application/json', 1)

    def test_html_not_mcp(self):
        with self.assertRaises(m.MCPError):
            m.read_response(io.BytesIO(b'<html>ok</html>'), 'text/html', 1)

    def test_wrong_project_rejected(self):
        with self.assertRaisesRegex(m.MCPError, 'identity'):
            m.verify_project('D:/Games/Other.uproject', 'D:/Games/Test.uproject')

    def test_project_path_normalized(self):
        m.verify_project('D:/Games/Test.uproject', 'd:\\games\\test.uproject')


if __name__ == '__main__':
    unittest.main()
