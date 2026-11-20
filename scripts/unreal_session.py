"""Discovery and identity guards for the observed UE 5.8 native toolsets."""
import ipaddress
import json
import ntpath
import re
import subprocess
from urllib.parse import urlsplit
from bridge_mcp import Client, MCPError, content, verify_project


def parse_toolsets(text):
    if not isinstance(text, str):
        raise MCPError('Unrecognized list_toolsets response; inspect the live schema')
    return list(dict.fromkeys(re.findall(r'^- (\w+(?:\.\w+)+):', text, re.M)))


def validate_inputs(schema, value, path='arguments'):
    kind = schema.get('type')
    types = {'object':dict, 'array':list, 'string':str, 'number':(int,float), 'integer':int, 'boolean':bool}
    if kind in types and (not isinstance(value, types[kind]) or (kind in ('number','integer') and isinstance(value,bool))):
        raise MCPError(f'{path} must be {kind}')
    if isinstance(value,dict):
        for key in schema.get('required',[]):
            if key not in value: raise MCPError(f'Missing required input {path}.{key}')
        for key, item in value.items():
            if key in schema.get('properties',{}):
                validate_inputs(schema['properties'][key],item,path+'.'+key)
    elif isinstance(value,list):
        for item in value: validate_inputs(schema.get('items',{}),item,path+'[]')
    if 'enum' in schema and value not in schema['enum']:
        raise MCPError(f'{path} not in advertised enum')


def listener_identity(endpoint):
    port = urlsplit(endpoint).port or 80
    command = f"""
$connections = @(Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue)
$rows = @($connections | ForEach-Object {{
  $process = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $_.OwningProcess)
  [pscustomobject]@{{LocalAddress=$_.LocalAddress;ProcessId=$_.OwningProcess;ExecutablePath=$process.ExecutablePath;CommandLine=$process.CommandLine}}
}})
ConvertTo-Json -InputObject $rows -Compress
"""
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],
                            capture_output=True,text=True,timeout=20,check=True)
    rows = json.loads(result.stdout)
    if not rows: raise MCPError('No local listener; open the editor and start MCP')
    if any(not ipaddress.ip_address(r['LocalAddress']).is_loopback for r in rows):
        raise MCPError('MCP port has a non-loopback listener; refusing all editor operations')
    if len({r['ProcessId'] for r in rows}) != 1:
        raise MCPError('Multiple processes own this MCP port; project identity is ambiguous')
    return rows[0]


def verify_process_identity(process, project, engine):
    expected_exe = ntpath.join(str(engine),'Engine','Binaries','Win64','UnrealEditor.exe')
    if ntpath.normcase(ntpath.normpath(process.get('ExecutablePath') or '')) != ntpath.normcase(ntpath.normpath(expected_exe)):
        raise MCPError('MCP listener is not the selected UnrealEditor executable')
    command = process.get('CommandLine') or ''
    paths = re.findall(r'"([^"\r\n]+\.uproject)"|([^\s"]+\.uproject)',command,re.I)
    if len(paths) != 1: raise MCPError('Cannot uniquely identify .uproject in editor command line')
    verify_project(paths[0][0] or paths[0][1],project)


class UnrealSession:
    def __init__(self, endpoint='http://127.0.0.1:8000/mcp', timeout=45):
        self.client = Client(endpoint,timeout)
        self.catalog = []
        self.identity = None

    def connect(self, full=False):
        initialized = self.client.initialize()
        self.top_tools = self.client.tools()
        top = {t['name']:t for t in self.top_tools}
        needed = {'list_toolsets','describe_toolset','call_tool'}
        if not needed.issubset(top):
            raise MCPError('Required tool-search interface missing. Enable bEnableToolSearch in Unreal MCP settings.')
        self.top = top
        validate_inputs(top['list_toolsets']['inputSchema'],{})
        names = parse_toolsets(content(self.client.call('list_toolsets',{})))
        self.names = names
        selected = ('SceneTools','ActorTools','AssetTools','ObjectTools','LogsToolset','EditorAppToolset')
        for name in names:
            if full or name.rsplit('.',1)[-1] in selected:
                arguments={'toolset_name':name}
                validate_inputs(top['describe_toolset']['inputSchema'],arguments)
                description = content(self.client.call('describe_toolset',arguments))
                if not isinstance(description,dict) or not isinstance(description.get('tools'),list):
                    raise MCPError('Invalid describe_toolset response: '+name)
                self.catalog.append(description)
        return initialized

    def tool(self, toolset, name):
        matches = [(d,t) for d in self.catalog if d['name'].split('.')[-1] == toolset
                   for t in d['tools'] if t['name'].split('.')[-1] == name]
        if len(matches)!=1: raise MCPError(f'Missing or ambiguous capability: {toolset}.{name}')
        return matches[0]

    def invoke(self, toolset, tool_name, **arguments):
        description,tool = self.tool(toolset,tool_name)
        validate_inputs(tool['inputSchema'],arguments)
        args={'toolset_name':description['name'],'tool_name':tool_name,'arguments':arguments}
        validate_inputs(self.top['call_tool']['inputSchema'],args)
        result = content(self.client.call('call_tool',args))
        return result['returnValue'] if isinstance(result,dict) and 'returnValue' in result else result

    def verify_identity(self, project, engine):
        process = listener_identity(self.client.endpoint)
        verify_process_identity(process,project,engine)
        # UE 5.8's category filter misses early unprefixed startup log lines.
        # Filter those lines with the advertised regex parameter instead.
        lines = self.invoke('LogsToolset','GetLogEntries',category='',
                            pattern='^LogInit:.*(Running engine for game:|Engine Version:|Base Directory:)',maxEntries=30)
        if not isinstance(lines,list): raise MCPError('No project identity log returned by MCP')
        if not any(line.endswith('Running engine for game: '+project.stem) for line in lines):
            raise MCPError('MCP current-session project name does not match selected project')
        if not any('Engine Version: 5.8.' in line and 'Compatible' not in line for line in lines):
            raise MCPError('MCP editor version is not verified as UE 5.8')
        self.identity={'project_file':str(project),'engine':str(engine),'listener':process,'mcp_log_entries':lines}
        return self.identity

    def capability_report(self):
        # Absent annotations are not permission to treat a tool as read-only.
        verified_reads = {
            ('SceneTools','get_current_level'),('SceneTools','find_actors'),
            ('ActorTools','get_actor_transform'),('ActorTools','get_label'),('ActorTools','get_components'),
            ('AssetTools','exists'),('AssetTools','find_assets'),('AssetTools','is_dirty'),
            ('ObjectTools','get_properties'),('ObjectTools','list_properties'),
            ('LogsToolset','GetLogEntries'),('EditorAppToolset','IsPIERunning'),
        }
        rows=[]
        for d in self.catalog:
            for t in d['tools']:
                readonly=t.get('annotations',{}).get('readOnlyHint') is True or (d['name'].split('.')[-1],t['name'].split('.')[-1]) in verified_reads
                rows.append({'toolset':d['name'],'tool':t['name'],'description':t.get('description',''),
                             'required_inputs':t['inputSchema'].get('required',[]),'input_schema':t['inputSchema'],
                             'output_schema':t.get('outputSchema'), 'availability':'discovered',
                             'classification':'read-only' if readonly else 'write',
                             'classification_basis':'reviewed read/schema hint' if readonly else 'conservative: may write; review before invocation'})
        return rows
