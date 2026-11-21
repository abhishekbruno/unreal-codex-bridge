"""Conservative, platform-neutral guards for native editor transitions."""
from pathlib import Path
from bridge_mcp import MCPError

class EditorStateGuard:
    def __init__(self, session, project, engine, owned):
        self.session = session
        self.project, self.engine = Path(project), Path(engine)
        self.owned = frozenset(owned)
        if not self.owned or any(not p.startswith('/Game/') or '..' in p for p in self.owned):
            raise ValueError('Explicit /Game/ task-owned package paths required')

    def inspect(self, target):
        s = self.session
        identity = s.verify_identity(self.project, self.engine)
        if target not in self.owned:
            raise MCPError('Target is not authorized for this task')
        if s.invoke('EditorAppToolset', 'IsPIERunning') is not False:
            raise MCPError('PIE running or unknown; transition blocked')
        active = s.invoke('SceneTools', 'get_current_level')
        if not active:
            raise MCPError('Active level unknown')
        dirty = {}
        for path in sorted(self.owned | {active}):
            if s.invoke('AssetTools', 'exists', path=path) or path == active:
                value = s.invoke('AssetTools', 'is_dirty', asset_path=path)
                if type(value) is not bool:
                    raise MCPError('Dirty state unknown: ' + path)
                dirty[path] = value
        return {'identity': identity, 'active_level': active, 'dirty': dirty,
                'coverage': 'Named packages only; external actor/sublevel dirtiness is not proven'}

    def save(self, path):
        self.inspect(path)
        if self.session.invoke('AssetTools', 'save_assets', asset_paths=[path]) is not True:
            raise MCPError('Save failed: ' + path)
        if self.session.invoke('AssetTools', 'is_dirty', asset_path=path) is not False:
            raise MCPError('Package remains dirty: ' + path)

    def transition(self, target, complete_world_state_verified=False):
        state = self.inspect(target)
        active = state['active_level']
        if state['dirty'].get(active):
            if active not in self.owned:
                raise MCPError('Unrelated dirty active level; preserve it before switching: ' + active)
            self.save(active)
        if not complete_world_state_verified:
            raise MCPError('Complete world dirty-state verification required before unloading a level')
        if state['dirty'].get(target):
            self.save(target)
        return state
