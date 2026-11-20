"""Small sequential Streamable HTTP MCP client. No server or editor emulation."""
import ipaddress
import json
import ntpath
import urllib.error
import urllib.parse
import urllib.request


class MCPError(RuntimeError):
    pass


def validate_endpoint(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'http' or p.username or p.password or p.query or p.fragment:
        raise ValueError('Only plain loopback HTTP MCP URLs without credentials/query/fragment are allowed')
    try:
        local = p.hostname == 'localhost' or ipaddress.ip_address(p.hostname).is_loopback
    except ValueError:
        local = False
    if not local or not p.path or (p.port is not None and not 1 <= p.port <= 65535):
        raise ValueError('MCP endpoint must be on loopback with an explicit path')
    return url


def unpack(message, request_id):
    if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or message.get('id') != request_id:
        raise MCPError('Invalid JSON-RPC response or mismatched response id')
    if 'error' in message:
        raise MCPError('JSON-RPC error: ' + json.dumps(message['error']))
    if 'result' not in message:
        raise MCPError('JSON-RPC response has no result')
    return message['result']


def read_response(stream, content_type, request_id):
    try:
        if 'application/json' in content_type:
            return unpack(json.load(stream), request_id)
        if 'text/event-stream' in content_type:
            data = []
            for line in stream:
                line = line.decode('utf-8').rstrip('\r\n')
                if line.startswith('data:'):
                    data.append(line[5:].lstrip(' '))
                elif not line and data:
                    message = json.loads('\n'.join(data))
                    data = []
                    if message.get('id') == request_id:
                        return unpack(message, request_id)
            raise MCPError('SSE stream ended without the requested response')
    except (ValueError, UnicodeError) as exc:
        raise MCPError(f'Malformed MCP response: {exc}') from exc
    raise MCPError(f'Unsupported MCP content type: {content_type}')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MCPError('MCP HTTP redirect refused: ' + str(code))


class Client:
    def __init__(self, endpoint='http://127.0.0.1:8000/mcp', timeout=30):
        self.endpoint = validate_endpoint(endpoint)
        self.timeout = timeout
        self.session = None
        self.protocol = None
        self.sequence = 0
        self.transcript = []
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, method, params=None, notification=False):
        self.sequence += 1
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        if not notification:
            payload['id'] = self.sequence
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        entry = {'request': payload}
        self.transcript.append(entry)
        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers=headers, method='POST')
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                session = response.headers.get('Mcp-Session-Id')
                if method == 'initialize' and session:
                    self.session = session
                if notification:
                    entry['http_status'] = response.status
                    return None
                result = read_response(response, response.headers.get('Content-Type', ''), payload['id'])
                entry['result'] = result
                return result
        except (urllib.error.URLError, TimeoutError, OSError, MCPError) as exc:
            entry['error'] = str(exc)
            raise MCPError(f'{method}: {exc}') from exc

    def initialize(self):
        result = self.request('initialize', {
            'protocolVersion': '2025-11-25', 'capabilities': {},
            'clientInfo': {'name': 'unreal-codex-bridge', 'version': '0.2.0'},
        })
        if not isinstance(result, dict) or not isinstance(result.get('serverInfo'), dict):
            raise MCPError('Invalid initialize result: missing serverInfo')
        self.protocol = result.get('protocolVersion')
        if self.protocol not in ('2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05'):
            raise MCPError(f'Unsupported negotiated protocol: {self.protocol}')
        self.request('notifications/initialized', notification=True)
        return result

    def tools(self):
        tools, seen, params = [], set(), {}
        while True:
            result = self.request('tools/list', params)
            if not isinstance(result, dict) or not isinstance(result.get('tools'), list):
                raise MCPError('Invalid tools/list result')
            tools.extend(result['tools'])
            cursor = result.get('nextCursor')
            if not cursor:
                return tools
            if cursor in seen:
                raise MCPError('Repeated tools/list pagination cursor')
            seen.add(cursor)
            params = {'cursor': cursor}

    def call(self, name, arguments):
        result = self.request('tools/call', {'name': name, 'arguments': arguments})
        if not isinstance(result, dict) or result.get('isError'):
            raise MCPError(f'Tool {name} failed: {json.dumps(result)}')
        return result


def content(result):
    if 'structuredContent' in result:
        return result['structuredContent']
    texts = [x['text'] for x in result.get('content', []) if x.get('type') == 'text']
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except ValueError:
            return texts[0]
    return texts


def verify_project(actual, expected):
    if not actual or ntpath.normcase(ntpath.abspath(actual)) != ntpath.normcase(ntpath.abspath(str(expected))):
        raise MCPError(f'Project identity mismatch: expected {expected!s}, got {actual!s}')
