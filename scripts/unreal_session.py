"""Discovery and identity guards for the observed UE 5.8 native toolsets."""
import ipaddress
import json
import ntpath
import os
from pathlib import Path
import platform
import posixpath
import re
import shutil
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
    if platform.system() == "Darwin":
        lsof_bin = shutil.which("lsof") or "/usr/sbin/lsof"
        try:
            res = subprocess.run([lsof_bin, "-nP", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-Fp"],
                                 capture_output=True, text=True, timeout=10, check=True)
            pids = [line[1:].strip() for line in res.stdout.splitlines() if line.startswith("p") and line[1:].strip().isdigit()]
            if not pids:
                raise MCPError('No local listener; open the editor and start MCP')
            if len(set(pids)) != 1:
                raise MCPError('Multiple processes own this MCP port; project identity is ambiguous')
            pid = int(pids[0])
            ps_res = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                    capture_output=True, text=True, timeout=5, check=True)
            cmdline = ps_res.stdout.strip()
            # Extract executable path from first argument
            exe_part = cmdline.split()[0] if cmdline else ""
            return {
                "LocalAddress": "127.0.0.1",
                "ProcessId": pid,
                "ExecutablePath": exe_part,
                "CommandLine": cmdline
            }
        except subprocess.SubprocessError as err:
            raise MCPError(f'Failed to inspect listener on macOS: {err}')

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
    exe_raw = process.get('ExecutablePath') or ''
    is_mac = (platform.system() == "Darwin") or ("/Mac/" in exe_raw or "\\Mac\\" in exe_raw)
    if is_mac:
        expected_mac_exe = posixpath.join(str(engine).replace('\\', '/'), 'Engine', 'Binaries', 'Mac', 'UnrealEditor.app', 'Contents', 'MacOS', 'UnrealEditor')
        norm_exe = exe_raw.replace('\\', '/')
        if norm_exe != expected_mac_exe and not norm_exe.endswith("UnrealEditor"):
            raise MCPError('MCP listener is not the selected UnrealEditor executable')
    else:
        expected_exe = ntpath.join(str(engine),'Engine','Binaries','Win64','UnrealEditor.exe')
        if ntpath.normcase(ntpath.normpath(exe_raw)) != ntpath.normcase(ntpath.normpath(expected_exe)):
            raise MCPError('MCP listener is not the selected UnrealEditor executable')

    command = process.get('CommandLine') or ''
    paths = re.findall(r'"([^"\r\n]+\.uproject)"|([^\s"]+\.uproject)',command,re.I)
    if len(paths) != 1: raise MCPError('Cannot uniquely identify .uproject in editor command line')
    project_arg = paths[0][0] or paths[0][1]
    if is_mac:
        if not posixpath.isabs(project_arg):
            raise MCPError('Editor project command-line path must be absolute')
    else:
        if not ntpath.isabs(project_arg) or not ntpath.splitdrive(project_arg)[0]:
            raise MCPError('Editor project command-line path must be absolute')
    verify_project(project_arg,project)


class UnrealSession:
    def __init__(self, endpoint='http://127.0.0.1:8000/mcp', timeout=45, auto_save=True):
        self.client = Client(endpoint,timeout)
        self.catalog = []
        self.identity = None
        self.auto_save_enabled = auto_save
        self._auto_save_manager = None

    @property
    def auto_save_manager(self):
        if self._auto_save_manager is None:
            from auto_save_manager import AutoSaveManager
            self._auto_save_manager = AutoSaveManager(self, enabled=self.auto_save_enabled)
        return self._auto_save_manager

    @auto_save_manager.setter
    def auto_save_manager(self, manager):
        self._auto_save_manager = manager

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

    def load_toolset(self, toolset):
        """Loads a toolset into the session catalog on-demand if not already loaded."""
        if not hasattr(self, 'names') or not self.names:
            raise MCPError('Session not connected or no toolsets discovered; call connect() first')
        for d in self.catalog:
            if d.get('name') == toolset or d.get('name', '').split('.')[-1] == toolset:
                return d
        matching = [n for n in self.names if n == toolset or n.split('.')[-1] == toolset]
        if not matching:
            raise MCPError(f'Unknown toolset: {toolset}')
        if len(matching) > 1:
            raise MCPError(f'Ambiguous toolset name: {toolset} matches {matching}')
        toolset_full_name = matching[0]
        arguments = {'toolset_name': toolset_full_name}
        validate_inputs(self.top['describe_toolset']['inputSchema'], arguments)
        description = content(self.client.call('describe_toolset', arguments))
        if not isinstance(description, dict) or not isinstance(description.get('tools'), list):
            raise MCPError('Invalid describe_toolset response: ' + toolset_full_name)
        self.catalog.append(description)
        return description

    def tool(self, toolset, name):
        desc = self.load_toolset(toolset)
        matches = [(desc, t) for t in desc.get('tools', [])
                   if t.get('name') == name or t.get('name', '').split('.')[-1] == name]
        if not matches:
            avail = [t.get('name', '').split('.')[-1] for t in desc.get('tools', [])]
            raise MCPError(f'Tool {name} not found in toolset {toolset}. Available: {avail}')
        if len(matches) > 1:
            raise MCPError(f'Ambiguous capability: {toolset}.{name}')
        return matches[0]

    def invoke(self, toolset, tool_name, **arguments):
        description,tool = self.tool(toolset,tool_name)
        validate_inputs(tool['inputSchema'],arguments)
        args={'toolset_name':description['name'],'tool_name':tool_name,'arguments':arguments}
        validate_inputs(self.top['call_tool']['inputSchema'],args)
        result = content(self.client.call('call_tool',args))
        ret_val = result['returnValue'] if isinstance(result,dict) and 'returnValue' in result else result
        if getattr(self, 'auto_save_enabled', False):
            from auto_save_manager import is_entity_creation_tool
            if is_entity_creation_tool(toolset, tool_name):
                self.auto_save_manager.handle_post_invoke(toolset, tool_name, arguments, ret_val)
        return ret_val

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

    def level_transaction(self, project, engine, target, journal, owned,
                          complete_world_state_verified=False):
        """Build a guarded level workflow using this connected transport."""
        from level_transaction import LevelTransaction
        return LevelTransaction(self, project, engine, target, journal, owned,
                                complete_world_state_verified)

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
