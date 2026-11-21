"""Resumable save-before-load sequence. No automatic discard or blind write retries."""
import json
import os
from pathlib import Path
from bridge_mcp import MCPError
from editor_state_guard import EditorStateGuard

class LevelTransaction:
    def __init__(self, session, project, engine, target, journal, owned, complete_world_state_verified=False):
        self.s, self.target = session, target
        self.guard = EditorStateGuard(session, project, engine, owned)
        self.path = Path(journal)
        self.world_verified = complete_world_state_verified
        self.state = {'project': str(Path(project)), 'target': target, 'events': []}
        if self.path.exists():
            previous = json.loads(self.path.read_text(encoding='utf8'))
            if previous['project'] != self.state['project'] or previous['target'] != target:
                raise MCPError('Journal identity mismatch')
            self.state = previous

    def record(self, stage, **details):
        self.state['events'].append({'stage': stage, **details})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with temp.open('w', encoding='utf8') as f:
            json.dump(self.state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)

    def run(self, source, execute, verify_execution):
        lock = self.path.with_suffix('.lock')
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            self.record('PREFLIGHT', state=self.guard.inspect(self.target))
            if not self.s.invoke('AssetTools', 'exists', path=self.target):
                # A pending create with unknown result requires inspection, not retry.
                if any(e['stage'] == 'CREATE_INTENT' for e in self.state['events']):
                    raise MCPError('Interrupted creation outcome unresolved; not retrying')
                self.record('CREATE_INTENT')
                if self.s.invoke('AssetTools', 'duplicate', path=source, new_path=self.target) is not True:
                    raise MCPError('Duplicate failed or outcome uncertain')
            self.record('SAVE')
            self.guard.save(self.target)
            self.record('VERIFY', dirty=False)
            self.guard.transition(self.target, self.world_verified)
            self.record('LOAD')
            try:
                self.s.invoke('SceneTools', 'load_level', level_path=self.target)
            except MCPError as exc:
                self.record('LOAD_ERROR', error=str(exc))
                expected = "Cannot load '" + self.target + "': the level has unsaved changes."
                if expected not in str(exc):
                    raise
                self.guard.transition(self.target, self.world_verified)
                self.guard.save(self.target)
                self.s.invoke('SceneTools', 'load_level', level_path=self.target)
            if self.s.invoke('SceneTools', 'get_current_level') != self.target:
                raise MCPError('Loaded level mismatch')
            self.record('VERIFY_LOADED')
            if not verify_execution():
                if any(e['stage'] == 'EXECUTE_INTENT' for e in self.state['events']):
                    raise MCPError('Interrupted execute requires reconciliation; not repeating writes')
                self.guard.inspect(self.target)
                self.record('EXECUTE_INTENT')
                execute()
            if not verify_execution():
                raise MCPError('Execution verification failed')
            self.record('SAVE_FINAL')
            self.guard.save(self.target)
            self.record('VERIFY_FINAL', persistence='saved; fresh reload not yet verified')
            return self.state
        except Exception as exc:
            self.record('BLOCKED', error=str(exc))
            raise
        finally:
            os.close(fd)
            lock.unlink()
