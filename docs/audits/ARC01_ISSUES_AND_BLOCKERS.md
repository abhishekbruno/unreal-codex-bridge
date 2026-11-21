# ARC 01 Issues, Fragilities & Blockers

**Audit Date:** 2026-11-21  
**Project:** Unreal Codex Bridge  
**Milestone:** ARC 01  

---

## 1. Prioritized Issues Summary

| Priority | Issue ID | Title | Component | Impact | Status |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **P0** | `BUG-01` | Missing `guard_listener_overrides` helper | `scripts/configure.py` | Unit test suite failure (1 error) | **RESOLVED & VERIFIED** (ARC 01.5) |
| **P0** | `BUG-02` | Windows CLI subprocess resolution | `scripts/doctor.py` | Diagnostics blocked on Windows (`WinError 2`) | **RESOLVED & VERIFIED** (ARC 01.5) |
| **P1** | `DES-01` | Hardcoded 6-toolset catalog limit | `scripts/unreal_session.py` | Uncataloged tools fail with capability error | **RESOLVED & VERIFIED** (ARC 01.5) |
| **P1** | `API-01` | `ObjectTools.get_properties` batch failure | `ObjectTools` | Property queries fail if any key is missing | **Workaround Verified** |
| **P1** | `NET-01` | Single port binding (Port 8000) | Server & Config | Collisions if multiple UE editors open | **Design Defined** |
| **P2** | `DEV-01` | Blueprint Graph DSL parsing | `skills/unreal-mcp` | Manual S-expression handling required | **Future Milestone** |
| **P3** | `OPS-01` | Missing CI workflow | Repository | Tests not run automatically on GitHub | **Future Milestone** |

---

## 2. Detailed Issue Analysis & Remediation

---

### [P0] BUG-01: Missing `guard_listener_overrides` in `scripts/configure.py`

#### Summary
`tests/test_configure.py::ConfigurationTests::test_public_port_override_rejected_before_configuration` fails with:
```
AttributeError: module 'configure' has no attribute 'guard_listener_overrides'
```

#### Root Cause
The security check was authored in `tests/test_configure.py` to assert that public listener configurations (e.g. `BindAddress=any` or non-loopback IPs) in `Config/DefaultEngine.ini` are detected and rejected before applying configurations. However, the implementation was omitted from `scripts/configure.py`.

#### Code Remediation (To be applied in `scripts/configure.py`):
```python
def guard_listener_overrides(paths, port):
    for path in paths:
        text = read(path)
        if not text:
            continue
        lines = text.splitlines()
        for line in lines:
            line_clean = line.strip()
            if 'ListenerOverrides' in line_clean and f'Port={port}' in line_clean:
                # Check if BindAddress is specified and non-loopback
                match = re.search(r'BindAddress\s*=\s*(?:"([^"]+)"|([^\s,\)]+))', line_clean)
                if match:
                    addr = match.group(1) or match.group(2)
                    if addr.lower() in ('any', '0.0.0.0', '*'):
                        raise ValueError(f'Public ListenerOverrides detected in {path.name}: {line_clean}')
                    try:
                        import ipaddress
                        if not ipaddress.ip_address(addr).is_loopback:
                            raise ValueError(f'Non-loopback ListenerOverrides detected in {path.name}: {line_clean}')
                    except ValueError:
                        if addr.lower() not in ('localhost', '127.0.0.1'):
                            raise ValueError(f'Invalid or public ListenerOverrides in {path.name}: {line_clean}')
```

---

### [P0] BUG-02: Windows CLI Subprocess Execution in `scripts/doctor.py`

#### Summary
Running `python scripts/doctor.py` on Windows results in:
```
BLOCKED codex_cli [WinError 2] The system cannot find the file specified
BLOCKED codex_configuration [WinError 2] The system cannot find the file specified
```

#### Root Cause
On Windows, Node/npm installs global command-line utilities with `.cmd` or `.ps1` wrappers (e.g. `C:\Users\<User>\AppData\Roaming\npm\codex.cmd`). In Python, calling `subprocess.check_output(['codex', '--version'])` without `shell=True` on Windows invokes the Win32 `CreateProcessW` API, which only searches for `.exe` files unless the full extension (`codex.cmd`) is explicitly supplied.

#### Code Remediation (To be applied in `scripts/doctor.py`):
```python
def resolve_codex_bin():
    # On Windows, prefer codex.cmd if codex.exe is not directly present
    bin_name = 'codex.cmd' if sys.platform == 'win32' else 'codex'
    resolved = shutil.which(bin_name) or shutil.which('codex')
    if not resolved:
        raise ValueError('Codex CLI absent from PATH')
    return resolved

def cli():
    bin_path = resolve_codex_bin()
    return subprocess.check_output([bin_path, '--version'], text=True, timeout=15).strip()

def config_check():
    ...
    bin_path = resolve_codex_bin()
    loaded = json.loads(subprocess.check_output([bin_path, 'mcp', 'list', '--json'], cwd=project.parent, text=True, timeout=30))
    ...
```

---

### [P1] DES-01: Hardcoded 6-Toolset Limit in `scripts/unreal_session.py`

#### Summary
Calling `session.invoke('BlueprintTools', ...)` or any tool outside the 6 initial toolsets fails with:
```
bridge_mcp.MCPError: Missing or ambiguous capability: BlueprintTools.get_graph_dsl_docs
```

#### Root Cause
In `scripts/unreal_session.py`, `connect(full=False)` pre-populates `self.catalog` only with:
```python
selected = ('SceneTools', 'ActorTools', 'AssetTools', 'ObjectTools', 'LogsToolset', 'EditorAppToolset')
```
If a script calls a tool in `BlueprintTools`, `UMGToolset`, `MaterialTools`, etc., the tool search fails because that toolset schema was never described.

#### Code Remediation:
Implement dynamic on-demand loading in `tool(toolset, name)`:
```python
def tool(self, toolset, name):
    # If not yet in catalog, dynamically describe on demand
    if not any(d['name'].split('.')[-1] == toolset for d in self.catalog):
        matching_ts = [n for n in self.names if n.split('.')[-1] == toolset]
        if matching_ts:
            args = {'toolset_name': matching_ts[0]}
            desc = content(self.client.call('call_tool', {'tool_name': 'describe_toolset', 'arguments': args}))
            if isinstance(desc, dict) and 'tools' in desc:
                self.catalog.append(desc)
    
    matches = [(d, t) for d in self.catalog if d['name'].split('.')[-1] == toolset
               for t in d['tools'] if t['name'].split('.')[-1] == name]
    if len(matches) != 1:
        raise MCPError(f'Missing or ambiguous capability: {toolset}.{name}')
    return matches[0]
```

---

### [P1] API-01: `ObjectTools.get_properties` Array Query Fragility

#### Summary
Calling `ObjectTools.get_properties(instance=comp, properties=['StaticMesh', 'static_mesh'])` fails with a hard error:
```
GetObjectProperties on '...': the following properties could not be read: static_mesh
```

#### Root Cause
Unreal Engine's C++ reflection handler inside `ObjectTools` checks all requested property names strictly. If any property does not exist on the target `UObject`, the entire tool call aborts with `isError: true` rather than returning a partial dictionary.

#### Best Practice / Workaround:
Always enumerate available property names using `ObjectTools.list_properties` first, match exact property names, and query properties individually or in pre-validated subsets.

---

### [P1] NET-01: Single Port Binding Collision

#### Summary
The default MCP port is `8000`. If a developer opens a second Unreal Engine editor session, the second session fails to bind to port 8000, causing silent server startup failure or port collision.

#### Planned Solution:
1. Support port offset search (8000, 8001, 8002).
2. Allow `scripts/doctor.py` and `scripts/live_test.py` to auto-discover active ports by inspecting listening sockets for `UnrealEditor.exe`.

