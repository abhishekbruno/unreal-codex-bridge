"""Offline protocol fixtures. These tests never count as Unreal live verification."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bridge_mcp import Client, MCPError


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.messages=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.messages.append((request,dict(self.headers)))
                if self.path=='/wrong':
                    self.send_error(404);return
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','http://example.com/mcp');self.end_headers();return
                method=request['method']
                if method=='notifications/initialized':
                    self.send_response(202);self.end_headers();return
                result={'jsonrpc':'2.0','id':request['id']}
                if method=='initialize':
                    result['result']={'protocolVersion':'2025-11-25','capabilities':{'tools':{}},'serverInfo':{'name':'OFFLINE-TEST-FIXTURE','version':'1'}}
                elif method=='tools/list':
                    result['result']={'tools':[{'name':'fixture-tool'}]}
                    if 'cursor' not in request.get('params',{}): result['result']['nextCursor']='page-2'
                else:
                    result['result']={'isError':True,'content':[{'type':'text','text':'fixture error'}]}
                payload=json.dumps(result).encode()
                ctype='application/json'
                if self.path=='/sse':payload=b'data: '+payload+b'\n\n';ctype='text/event-stream'
                self.send_response(200);self.send_header('Content-Type',ctype)
                self.send_header('Content-Length',str(len(payload)))
                if method=='initialize':self.send_header('Mcp-Session-Id','fixture-session')
                self.end_headers();self.wfile.write(payload)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def test_real_http_session_headers_and_pagination(self):
        c=Client(self.url+'/mcp');c.initialize();self.assertEqual(len(c.tools()),2)
        self.assertEqual(self.messages[1][0]['method'],'notifications/initialized')
        headers={k.lower():v for k,v in self.messages[2][1].items()}
        self.assertEqual(headers['mcp-session-id'],'fixture-session')
        self.assertEqual(headers['mcp-protocol-version'],'2025-11-25')

    def test_real_sse_initialization(self):
        self.assertEqual(Client(self.url+'/sse').initialize()['serverInfo']['name'],'OFFLINE-TEST-FIXTURE')

    def test_incorrect_endpoint_returns_transport_error(self):
        with self.assertRaisesRegex(MCPError,'404'): Client(self.url+'/wrong').initialize()

    def test_no_redirect_to_remote_server(self):
        with self.assertRaisesRegex(MCPError,'redirect refused'): Client(self.url+'/redirect').initialize()

    def test_error_tool_result_is_failure(self):
        c=Client(self.url+'/mcp');c.initialize()
        with self.assertRaisesRegex(MCPError,'fixture error'):c.call('bad',{})

    def test_closed_server_is_not_operational(self):
        self.server.shutdown();self.server.server_close()
        with self.assertRaises(MCPError):Client(self.url+'/mcp',timeout=.5).initialize()


if __name__=='__main__':unittest.main()
