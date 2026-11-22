"""Read-only ARC 01 checks. A PASS means inspection-ready, not live-test acceptance."""
import argparse
import json
import shutil
import socket
import subprocess
import sys
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        from compat_toml import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from bridge_mcp import MCPError, validate_endpoint
from configure import matching_servers
from unreal_session import UnrealSession

PLUGIN_PATHS = {
    'ModelContextProtocol':'Engine/Plugins/Experimental/ModelContextProtocol/ModelContextProtocol.uplugin',
    'AllToolsets':'Engine/Plugins/Experimental/Toolsets/AllToolsets/AllToolsets.uplugin',
    'ToolsetRegistry':'Engine/Plugins/Experimental/ToolsetRegistry/ToolsetRegistry.uplugin',
}


def check_engine(engine):
    build = engine/'Engine/Build/Build.version'
    if not build.is_file(): raise ValueError('Engine Build.version missing; finish installing UE 5.8')
    version=json.loads(build.read_text(encoding='utf-8-sig'))
    if (version.get('MajorVersion'),version.get('MinorVersion'))!=(5,8):
        raise ValueError('This ARC targets Unreal Engine 5.8 only')
    has_win_exe = (engine/'Engine/Binaries/Win64/UnrealEditor.exe').is_file()
    has_mac_exe = (engine/'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor').is_file()
    if sys.platform == 'darwin':
        if not has_mac_exe and not has_win_exe:
            raise ValueError('UnrealEditor executable is missing on macOS')
    else:
        if not has_win_exe and not has_mac_exe:
            raise ValueError('UnrealEditor.exe is missing')
    for name,path in PLUGIN_PATHS.items():
        if not (engine/path).is_file(): raise ValueError('Missing required native plugin: '+name)
        json.loads((engine/path).read_text(encoding='utf-8-sig'))
    return version


def resolve_codex_bin():
    """Resolve Codex CLI executable safely across Windows, Linux, and macOS."""
    if sys.platform == 'win32':
        # On Windows, npm global CLIs have .cmd wrappers or .exe
        resolved = shutil.which('codex.cmd') or shutil.which('codex.exe') or shutil.which('codex')
    else:
        resolved = shutil.which('codex')
    if not resolved:
        raise ValueError('Codex CLI absent from PATH')
    return resolved


def result_code(checks):
    statuses={c['status'] for c in checks}
    return 1 if 'FAIL' in statuses else 2 if statuses & {'BLOCKED','NOT TESTED'} else 0


def run(project, engine, endpoint, full=False):
    checks=[]
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'endpoint':endpoint,'checks':checks,
            'live_creation':'NOT TESTED: run scripts/live_test.py separately'}
    def check(name,action,missing='FAIL'):
        try:
            value=action();checks.append({'name':name,'status':'PASS','detail':value});return value
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
            checks.append({'name':name,'status':missing,'detail':str(exc)});return None
    check('python',lambda:sys.version)
    def cli():
        bin_path = resolve_codex_bin()
        try:
            return subprocess.check_output([bin_path, '--version'], text=True, timeout=15).strip()
        except subprocess.CalledProcessError as exc:
            raise ValueError(f'Codex CLI version check failed (exit code {exc.returncode}): {exc.output}') from exc
        except OSError as exc:
            raise ValueError(f'Failed to execute Codex CLI at {bin_path}: {exc}') from exc
    check('codex_cli',cli,'BLOCKED')
    def project_check():
        if not project or not project.is_file() or project.suffix.lower()!='.uproject':
            raise ValueError('Supply the full path to an existing target .uproject')
        d=json.loads(project.read_text(encoding='utf-8-sig'))
        enabled={p['Name']:p.get('Enabled') for p in d.get('Plugins',[])}
        for name in ('ModelContextProtocol','AllToolsets'):
            if enabled.get(name) is not True: raise ValueError(name+' is not enabled')
        if enabled.get('ToolsetRegistry') is False: raise ValueError('ToolsetRegistry dependency explicitly disabled')
        return {'path':str(project),'plugins':enabled}
    project_data=check('project_and_plugins',project_check,'BLOCKED')
    version=check('engine',lambda:check_engine(engine),'BLOCKED')
    def config_check():
        if not project_data: raise ValueError('Project unavailable')
        path=project.parent/'.codex/config.toml'
        data=tomllib.loads(path.read_text(encoding='utf-8-sig'))
        matches=matching_servers(data,endpoint)
        if len(matches)!=1: raise ValueError('Expected exactly one project MCP registration for endpoint')
        if data['mcp_servers'][matches[0]].get('enabled') is False: raise ValueError('MCP registration disabled')
        bin_path = resolve_codex_bin()
        try:
            cmd_out = subprocess.check_output([bin_path, 'mcp', 'list', '--json'], cwd=project.parent, text=True, timeout=30)
            loaded = json.loads(cmd_out)
        except subprocess.CalledProcessError as exc:
            raise ValueError(f'Failed to query Codex MCP list (exit code {exc.returncode}): {exc.output}') from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f'Malformed JSON from Codex MCP list: {exc}') from exc
        matching=[s for s in loaded if s['name']==matches[0] and s.get('enabled') and s.get('transport',{}).get('url')==data['mcp_servers'][matches[0]]['url']]
        if len(matching)!=1: raise ValueError('Codex did not load the intended server; check project trust and overrides')
        return {'path':str(path),'server':matches[0],'recognized_by_codex':True}
    check('codex_configuration',config_check,'BLOCKED')
    valid=check('loopback_endpoint',lambda:validate_endpoint(endpoint))
    def tcp():
        p=urlsplit(endpoint)
        with socket.create_connection((p.hostname,p.port or 80),timeout=3): return 'Reachable; not proof of MCP'
    if valid: check('tcp',tcp)
    session=UnrealSession(endpoint) if valid else None
    init=check('mcp_initialization_and_discovery',lambda:session.connect(full)) if session else None
    if init is not None:
        report['initialization']=init
        report['capabilities']=session.capability_report()
        report['toolset_names']=session.names
        identity=check('active_project_identity',lambda:session.verify_identity(project,engine)) if project_data and version else None
        if identity:
            report['identity']=identity
            check('current_level',lambda:session.invoke('SceneTools','get_current_level'))
            check('actor_listing',lambda:session.invoke('SceneTools','find_actors',name='',tag='',collision_channels=[]))
        else:
            checks.append({'name':'scene_inspection','status':'BLOCKED','detail':'Project identity was not verified'})
    else:
        checks.append({'name':'active_project_identity','status':'BLOCKED','detail':'No initialized MCP session'})
        checks.append({'name':'scene_inspection','status':'NOT TESTED','detail':'No initialized MCP session'})
    if session: report['transcript']=session.client.transcript
    report['exit_code']=result_code(checks)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--endpoint',default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--full',action='store_true',help='Describe all toolsets sequentially')
    parser.add_argument('--output',type=Path,default=Path('evidence/doctor.json'))
    args=parser.parse_args()
    report=run(args.project.resolve(),args.engine.resolve(),args.endpoint,args.full)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for c in report['checks']:
        detail=c['detail']
        if c['name']=='actor_listing' and isinstance(detail,list): detail=f'{len(detail)} actors'
        print(c['status'],c['name'],str(detail)[:500])
    print('Evidence:',args.output.resolve())
    return report['exit_code']


if __name__=='__main__': raise SystemExit(main())
