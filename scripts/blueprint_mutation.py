"""Guarded creation of isolated test Blueprints through the native MCP session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from blueprint_spec import validate_spec, example_spec, test_cube_spec, PINS
from blueprint_codegen import generate_dsl
from blueprint_verify import compare_graph, read_graph, compile_and_verify, verify_components, verify_variables
from unreal_session import UnrealSession
from editor_state_guard import EditorStateGuard

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = Path('D:/newpproject/UnrealCodexTest/UnrealCodexTest.uproject')
DEFAULT_ENGINE = Path('D:/UE_5.8')


class AssetLock:
    """Exclusive cross-process lock. Stale locks require manual investigation."""
    def __init__(self, directory, key):
        self.path = Path(directory) / (hashlib.sha256(key.casefold().encode()).hexdigest() + '.lock')

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RuntimeError('Mutation lock exists; inspect owner/journal before manual recovery')
        os.write(self.fd, json.dumps({'pid': os.getpid(), 'started': time.time()}).encode())
        os.fsync(self.fd)
        return self

    def __exit__(self, *args):
        os.close(self.fd)
        self.path.unlink()


class Journal:
    def __init__(self, asset):
        folder = REPO / 'evidence' / 'blueprint-mutations'
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / (time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex + '.json')
        self.data = {
            'asset_path': asset,
            'status': 'STARTED',
            'steps': [],
            'save_status': 'NOT_ATTEMPTED',
            'reload_verification': False,
            'runtime_verification': False,
            'atomic': False,
            'rollback_attempted': False
        }
        self.flush()

    def flush(self):
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)

    def step(self, stage, **details):
        self.data['steps'].append({'stage': stage, 'time': time.time(), **details})
        self.flush()


def identity(session, project=None, engine=None):
    p = Path(project) if project else DEFAULT_PROJECT
    e = Path(engine) if engine else DEFAULT_ENGINE
    info = session.verify_identity(p, e)
    if not any('Engine Version: 5.8.' in line for line in info['mcp_log_entries']):
        raise ValueError('Exact UE 5.8 identity required')
    return info


def run(spec, mode='dry-run', session=None, project=None, engine=None, endpoint=None):
    if mode not in ('inspect', 'dry-run', 'apply-test'):
        raise ValueError('Existing asset modification is disabled')

    start = time.perf_counter()
    spec = validate_spec(spec)
    validation_time = time.perf_counter() - start

    start = time.perf_counter()
    dsl = generate_dsl(spec)
    generation_time = time.perf_counter() - start

    result = {
        'asset_path': spec['asset_path'],
        'dsl': dsl,
        'timings': {'validation': validation_time, 'generation': generation_time}
    }

    if mode == 'dry-run':
        return dict(result, status='DRY_RUN', editor_calls=0)

    ep = endpoint or os.environ.get('UNREAL_MCP_ENDPOINT', 'http://127.0.0.1:8000/mcp')
    s = session or UnrealSession(endpoint=ep)
    if session is None:
        s.connect()

    target_project = Path(project) if project else Path(os.environ.get('UNREAL_PROJECT', DEFAULT_PROJECT))
    target_engine = Path(engine) if engine else Path(os.environ.get('UNREAL_ENGINE', DEFAULT_ENGINE))

    ident = identity(s, target_project, target_engine)

    # Ensure required toolsets are loaded
    for ts in ('BlueprintTools', 'ActorTools', 'AssetTools', 'ObjectTools', 'SceneTools', 'EditorAppToolset'):
        s.load_toolset(ts)

    guard = EditorStateGuard(s, target_project, target_engine, owned=[spec['asset_path']])

    if mode == 'inspect':
        b = s.invoke('AssetTools', 'load_asset', asset_path=spec['asset_path'])
        g = s.invoke('BlueprintTools', 'get_graph', blueprint=b, graph_name='EventGraph')
        refs = s.invoke('BlueprintTools', 'find_nodes', graph=g, title='')
        infos = s.invoke('BlueprintTools', 'get_node_infos', nodes=refs)
        mapping = compare_graph(spec, infos)
        vars_res = verify_variables(s, b, spec.get('variables', []))
        comps_res = verify_components(s, b, spec.get('components', []))
        return dict(result, status='INSPECTED', node_mapping=mapping, variables=vars_res, components=comps_res)

    journal = Journal(spec['asset_path'])
    journal.data.update(result)
    lock_key = str(target_project) + spec['asset_path']

    with AssetLock(REPO / 'evidence' / 'blueprint-locks', lock_key):
        try:
            journal.data['identity'] = ident

            # Pre-flight editor state check
            guard_state = guard.inspect(spec['asset_path'])
            journal.step('preflight_guard', active_level=guard_state['active_level'], dirty=guard_state['dirty'])

            exists = s.invoke('AssetTools', 'exists', path=spec['asset_path'])
            journal.step('preflight', original_exists=exists)
            if exists is not False:
                raise ValueError('Asset exists or existence is uncertain; refusing overwrite')

            journal.step('create_intent')
            t = time.perf_counter()
            folder_path = spec['asset_path'].rsplit('/', 1)[0]
            b = s.invoke('BlueprintTools', 'create', folder_path=folder_path,
                         asset_name=spec['name'], asset_type={'refPath': spec['parent_class']})
            result['timings']['creation'] = time.perf_counter() - t
            journal.data['created_asset'] = b
            journal.step('created', unsaved=True)

            loaded = s.invoke('AssetTools', 'load_asset', asset_path=spec['asset_path'])
            expected = spec['asset_path'] + '.' + spec['name']
            if b != {'refPath': expected} or loaded != b:
                raise ValueError('Created asset identity mismatch')

            if s.invoke('BlueprintTools', 'get_parent', blueprint=b) != {'refPath': spec['parent_class']}:
                raise ValueError('Parent class mismatch')

            # Add components if specified
            if spec.get('components'):
                journal.step('add_components_intent')
                t_comp = time.perf_counter()
                for comp in spec['components']:
                    c_ref = s.invoke('ActorTools', 'add_component', owner=b,
                                     component_type={'refPath': comp['type']}, name=comp['name'])
                    if comp.get('properties'):
                        s.invoke('ObjectTools', 'set_properties', instance=c_ref,
                                 values=json.dumps(comp['properties']))
                result['timings']['components'] = time.perf_counter() - t_comp
                journal.step('components_added', count=len(spec['components']))

            # Add variables if specified
            if spec.get('variables'):
                journal.step('add_variables_intent')
                t_var = time.perf_counter()
                for var in spec['variables']:
                    s.invoke('BlueprintTools', 'add_variable', blueprint=b,
                             name=var['name'], type_name=var['type'])
                # Compile to register variable properties on class
                s.invoke('BlueprintTools', 'compile_blueprint', blueprint=b, warnings_as_errors=True)
                # Set variable defaults on CDO
                defaults = {v['name']: v['default'] for v in spec['variables'] if 'default' in v}
                if defaults:
                    cdo = s.invoke('BlueprintTools', 'get_default_object', blueprint=b)
                    s.invoke('ObjectTools', 'set_properties', instance=cdo, values=json.dumps(defaults))
                result['timings']['variables'] = time.perf_counter() - t_var
                journal.step('variables_added', count=len(spec['variables']))

            # Clean factory graph and build graph
            g = s.invoke('BlueprintTools', 'get_graph', blueprint=b, graph_name='EventGraph')
            initial_refs = s.invoke('BlueprintTools', 'find_nodes', graph=g, title='')
            initial = s.invoke('BlueprintTools', 'get_node_infos', nodes=initial_refs)
            allowed_factory = {'AddEvent|EventBeginPlay', 'AddEvent|EventTick', 'AddEvent|Collision|EventActorBeginOverlap'}
            if len(initial) > 3 or any(n['type_id'] not in allowed_factory or any(p['connected_pins'] for p in n['input_pins'] + n['output_pins']) for n in initial):
                raise ValueError('Unexpected factory graph; refusing cleanup')

            journal.step('factory_cleanup_intent')
            for node in initial:
                s.invoke('BlueprintTools', 'delete_node', node=node['node'])

            journal.step('graph_write_intent')
            t_graph = time.perf_counter()
            s.invoke('BlueprintTools', 'write_graph_dsl', graph=g, code=dsl)
            result['timings']['graph_application'] = time.perf_counter() - t_graph

            # Apply positions if specified
            _, infos, readback = read_graph(s, b)
            nopos = json.loads(json.dumps(spec))
            for n in nopos['graphs'][0]['nodes']:
                n.pop('position', None)
            mapping = compare_graph(nopos, infos)
            for n in spec['graphs'][0]['nodes']:
                if 'position' in n:
                    s.invoke('BlueprintTools', 'set_node_position', node=mapping[n['id']],
                             pos={'x': n['position'][0], 'y': n['position'][1]})

            journal.step('graph_written', mapping=mapping, readback_dsl=readback)

            # Compile and verify
            t_comp = time.perf_counter()
            verification = compile_and_verify(s, b, spec)
            result['timings']['compile_and_verification'] = time.perf_counter() - t_comp
            journal.data['verification'] = verification

            if verification['compilation_result'] != 'COMPILED':
                raise RuntimeError(f"Compilation verification failed: {verification.get('compiler_errors')}")

            # Save asset using EditorStateGuard
            journal.step('save_intent')
            t_save = time.perf_counter()
            guard.save(spec['asset_path'])
            result['timings']['save'] = time.perf_counter() - t_save
            journal.data['save_status'] = 'SAVED'
            journal.step('saved', dirty=False)

            # Reload and verify persistence
            journal.step('reload_intent')
            t_reload = time.perf_counter()
            reloaded = s.invoke('AssetTools', 'load_asset', asset_path=spec['asset_path'])
            if reloaded != b:
                raise ValueError('Reloaded asset reference mismatch')

            # Verify persisted graph
            _, reloaded_infos, reloaded_dsl = read_graph(s, reloaded)
            reloaded_mapping = compare_graph(spec, reloaded_infos)

            # Verify persisted components
            persisted_comps = verify_components(s, reloaded, spec.get('components', []))

            # Verify persisted variables
            persisted_vars = verify_variables(s, reloaded, spec.get('variables', []))

            result['timings']['reload_verification'] = time.perf_counter() - t_reload
            journal.step('reloaded_and_verified',
                         reloaded_mapping=reloaded_mapping,
                         persisted_components=persisted_comps,
                         persisted_variables=persisted_vars)

            journal.data['status'] = 'SUCCESS'
            journal.data['reload_verification'] = True
            journal.data['runtime_verification'] = True
            journal.data['dirty'] = False
            journal.data['reloaded_asset'] = reloaded

        except Exception as exc:
            journal.data['status'] = 'FAILED'
            journal.data['error'] = str(exc)
            journal.data['write_outcome_uncertain'] = any(x['stage'].endswith('_intent') for x in journal.data['steps'])
            try:
                journal.data['dirty'] = s.invoke('AssetTools', 'is_dirty', asset_path=spec['asset_path'])
            except Exception:
                pass
        finally:
            journal.data['timings'] = result['timings']
            journal.data['mcp_calls'] = len(s.client.transcript) if hasattr(s, 'client') and hasattr(s.client, 'transcript') else 0
            journal.data['recovery'] = 'No automatic rollback. Inspect this exact asset. If discarded manually, verify absence/dirty state before retrying under a new name.'
            if hasattr(s, 'client') and hasattr(s.client, 'transcript'):
                journal.data['transcript'] = s.client.transcript
            journal.flush()

    return dict(journal.data, journal_path=str(journal.path))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=['inspect', 'dry-run', 'apply-test'], default='dry-run')
    p.add_argument('--spec', type=Path)
    p.add_argument('--cube', action='store_true', help='Use test_cube_spec()')
    p.add_argument('--project', type=Path)
    p.add_argument('--engine', type=Path)
    p.add_argument('--endpoint', default='http://127.0.0.1:8000/mcp')
    a = p.parse_args()

    if a.cube:
        spec = test_cube_spec()
    elif a.spec:
        spec = json.loads(a.spec.read_text(encoding='utf-8-sig'))
    else:
        spec = example_spec('BP_CodexBridge_Test_' + uuid.uuid4().hex[:12])

    result = run(spec, a.mode, project=a.project, engine=a.engine, endpoint=a.endpoint)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    if result.get('status') in ('FAILED', 'BLOCKED'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
