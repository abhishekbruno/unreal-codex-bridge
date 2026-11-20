"""Backed-up project configuration. Does not install plugins or change global Codex settings."""
import argparse
import json
import re
import shutil
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from bridge_mcp import validate_endpoint


def read(path):
    return path.read_bytes().decode('utf-8-sig') if path.exists() else ''


def write_backed_up(path, text):
    payload = text.encode('utf-8')
    if path.exists() and path.read_bytes() == payload:
        return None
    backup = None
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = path.with_name(path.name + '.backup-' + stamp)
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return str(backup) if backup else 'new file'


def plugin_content(original):
    data = json.loads(original)
    entries = data.setdefault('Plugins', [])
    if not isinstance(entries, list) or any(not isinstance(p, dict) for p in entries):
        raise ValueError('Plugins must be an array of objects')
    changed = False
    for name in ('ModelContextProtocol', 'AllToolsets', 'ToolsetRegistry'):
        matches = [p for p in entries if p.get('Name') == name]
        if len(matches) > 1:
            raise ValueError('Duplicate plugin declaration: ' + name)
        if matches:
            if matches[0].get('Enabled') is not True:
                matches[0]['Enabled'] = True
                changed = True
        elif name != 'ToolsetRegistry':  # Native MCP plugin already declares this dependency.
            entries.append({'Name': name, 'Enabled': True})
            changed = True
    return json.dumps(data, indent=2) + '\n' if changed else original


def endpoint_key(url):
    p = urlsplit(validate_endpoint(url))
    return ('loopback', p.port or 80, p.path.rstrip('/'))


def matching_servers(document, endpoint):
    matches = []
    for name, settings in document.get('mcp_servers', {}).items():
        try:
            if endpoint_key(settings.get('url', '')) == endpoint_key(endpoint):
                matches.append(name)
        except (ValueError, TypeError):
            pass
    return matches


def codex_content(original, endpoint):
    validate_endpoint(endpoint)
    data = tomllib.loads(original)
    matches = matching_servers(data, endpoint)
    if len(matches) > 1:
        raise ValueError('Duplicate MCP registrations: ' + ', '.join(matches))
    if matches:
        if data['mcp_servers'][matches[0]].get('enabled') is False:
            raise ValueError('Existing Unreal registration is disabled; review before enabling')
        return original
    if 'unreal-mcp' in data.get('mcp_servers', {}):
        raise ValueError('Existing unreal-mcp endpoint differs; reconcile explicitly')
    result = original + '\n[mcp_servers.unreal-mcp]\nurl = ' + json.dumps(endpoint) + '\n'
    tomllib.loads(result)
    return result


def ini_content(original, section, settings):
    lines = original.splitlines(keepends=True)
    headers = [i for i, line in enumerate(lines) if line.strip() == '[' + section + ']']
    if len(headers) > 1:
        raise ValueError('Duplicate INI section: ' + section)
    if not headers:
        return original + ('\n' if original and not original.endswith('\n') else '') + '\n[' + section + ']\n' + ''.join(f'{k}={v}\n' for k,v in settings.items())
    start = headers[0] + 1
    end = next((i for i in range(start, len(lines)) if lines[i].lstrip().startswith('[')), len(lines))
    body = ''.join(lines[start:end])
    for key, value in settings.items():
        pattern = re.compile(r'(?m)^' + re.escape(key) + r'\s*=[^\r\n]*')
        if len(pattern.findall(body)) > 1:
            raise ValueError('Duplicate INI key: ' + key)
        if pattern.search(body):
            body = pattern.sub(key + '=' + value, body)
        else:
            body += ('' if not body or body.endswith('\n') else '\n') + key + '=' + value + '\n'
    return ''.join(lines[:start]) + body + ''.join(lines[end:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--apply', action='store_true', help='Without this, only preview the planned file changes')
    args = parser.parse_args()
    try:
        from doctor import check_engine
        check_engine(args.engine)
        project = args.project.resolve()
        if not project.is_file() or project.suffix.lower() != '.uproject':
            raise ValueError('Provide an existing .uproject')
        p = urlsplit(validate_endpoint(args.endpoint))
        root = project.parent
        cfg = root / '.codex/config.toml'
        ini = root / 'Config/DefaultEditorPerProjectUserSettings.ini'
        engine_ini = root / 'Config/DefaultEngine.ini'
        # Validate all planned content before the first write.
        changes = {
            project: plugin_content(read(project)),
            cfg: codex_content(read(cfg), args.endpoint),
            ini: ini_content(read(ini), '/Script/ModelContextProtocolEngine.ModelContextProtocolSettings', {
                'bAutoStartServer':'True','ServerPortNumber':str(p.port or 80),'ServerUrlPath':p.path}),
            engine_ini: ini_content(read(engine_ini), 'HTTPServer.Listeners', {'DefaultBindAddress':'127.0.0.1'}),
        }
        for path, text in changes.items():
            if read(path) == text:
                print('UNCHANGED', path)
            elif args.apply:
                print('CHANGED', path, 'backup:', write_backed_up(path, text))
            else:
                print('WOULD CHANGE', path)
        return 0
    except (OSError, ValueError) as exc:
        print('FAIL:', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
