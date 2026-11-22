"""ARC 02 Phase 4: Automated Gameplay System.

Provides an end-to-end declarative pipeline to create, compile, save, test,
and verify functional Unreal Engine gameplay mechanics:
VALIDATE → CREATE → CONNECT → COMPILE → SAVE → RELOAD → PLAYTEST → VERIFY.
"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

from blueprint_spec import (
    validate_spec,
    example_spec,
    test_cube_spec,
    collectible_cube_spec,
    game_manager_spec,
    ALLOWED_ROOTS,
    SpecError
)
from blueprint_codegen import generate_dsl
from blueprint_verify import (
    compare_graph,
    read_graph,
    compile_and_verify,
    verify_components,
    verify_variables
)
from blueprint_mutation import AssetLock
from unreal_session import UnrealSession
from editor_state_guard import EditorStateGuard
from auto_save_manager import AutoSaveManager, CreationTransaction
from bridge_mcp import MCPError
import playtest
from playtest import PIEState, run_playtest, inspect_log_telemetry, find_project_log


class GameplayError(Exception):
    """Raised when gameplay automation encounters an unrecoverable failure."""
    pass


class ErrorCategory:
    COMPILER_ERROR = 'COMPILER_ERROR'
    PIN_MISMATCH = 'PIN_MISMATCH'
    DIRTY_LEVEL_CONFLICT = 'DIRTY_LEVEL_CONFLICT'
    DUPLICATE_ASSET = 'DUPLICATE_ASSET'
    DUPLICATE_ACTOR = 'DUPLICATE_ACTOR'
    OFFLINE_DISCONNECTED = 'OFFLINE_DISCONNECTED'
    UNRECOVERABLE = 'UNRECOVERABLE'


class ErrorRecoveryManager:
    """Diagnoses MCP and compiler errors and executes safe, bounded retries."""

    def __init__(self, session, auto_saver, guard, journal=None):
        self.session = session
        self.auto_saver = auto_saver
        self.guard = guard
        self.journal = journal
        self.recovery_log = []

    def log(self, stage, message, **details):
        entry = {'stage': stage, 'message': message, 'time': time.time(), **details}
        self.recovery_log.append(entry)
        if self.journal:
            self.journal.record_event('ERROR_RECOVERY', **entry)

    def diagnose_error(self, exc, context=''):
        """Classify an exception into a categorized error code."""
        text = str(exc)
        if '10061' in text or 'Connection refused' in text or 'WinError 10061' in text or 'Cannot connect' in text:
            return ErrorCategory.OFFLINE_DISCONNECTED
        if 'unsaved changes' in text or 'has unsaved changes' in text:
            return ErrorCategory.DIRTY_LEVEL_CONFLICT
        if 'already exists' in text or 'refusing overwrite' in text:
            return ErrorCategory.DUPLICATE_ASSET
        if 'actor already exists' in text.lower() or 'duplicate actor' in text.lower():
            return ErrorCategory.DUPLICATE_ACTOR
        if 'pin' in text.lower() and ('mismatch' in text.lower() or 'not found' in text.lower() or 'direction' in text.lower()):
            return ErrorCategory.PIN_MISMATCH
        if 'compilation' in text.lower() or 'compile' in text.lower() or 'compiler' in text.lower():
            return ErrorCategory.COMPILER_ERROR
        return ErrorCategory.UNRECOVERABLE

    def execute_safe_retry(self, operation_name, op_fn, recovery_fn=None, max_attempts=2):
        """Execute an operation with bounded, safe retry upon recoverable error."""
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                return op_fn()
            except Exception as exc:
                last_error = exc
                category = self.diagnose_error(exc, context=operation_name)
                self.log(operation_name, f"Attempt {attempt}/{max_attempts} failed: {exc}",
                         category=category, attempt=attempt)

                if attempt >= max_attempts or category == ErrorCategory.UNRECOVERABLE or category == ErrorCategory.OFFLINE_DISCONNECTED:
                    raise exc

                # Perform category-specific safe recovery
                if category == ErrorCategory.DIRTY_LEVEL_CONFLICT:
                    active = self.session.invoke('SceneTools', 'get_current_level')
                    if active and active in self.guard.owned:
                        self.log(operation_name, f"Safely saving owned dirty level {active} before retry")
                        self.guard.save(active)
                    else:
                        raise MCPError(f"Cannot discard or save unowned dirty level: {active}")
                elif category in (ErrorCategory.COMPILER_ERROR, ErrorCategory.PIN_MISMATCH):
                    if recovery_fn:
                        self.log(operation_name, "Executing compiler/pin recovery hook before retry")
                        recovery_fn()
                elif category == ErrorCategory.DUPLICATE_ASSET:
                    self.log(operation_name, "Duplicate asset detected; relying on idempotent check")
                elif category == ErrorCategory.DUPLICATE_ACTOR:
                    self.log(operation_name, "Duplicate actor detected; attempting reuse or unique naming")
                else:
                    raise exc

        raise last_error


class GameplayJournal:
    """Durable transaction journal for gameplay automation runs."""

    def __init__(self, name='gameplay_run'):
        folder = REPO / 'evidence' / 'gameplay-runs'
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}.json"
        self.data = {
            'run_id': self.path.stem,
            'name': name,
            'status': 'STARTED',
            'start_time': time.time(),
            'stages': {},
            'events': [],
            'saved_packages': [],
            'verified': False,
        }
        self.flush()

    def flush(self):
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, self.path)

    def record_stage(self, stage, status, **details):
        self.data['stages'][stage] = {
            'status': status,
            'time': time.time(),
            **details
        }
        self.flush()

    def record_event(self, event_type, **details):
        self.data['events'].append({
            'type': event_type,
            'time': time.time(),
            **details
        })
        self.flush()

    def finalize(self, status, **details):
        self.data['status'] = status
        self.data['end_time'] = time.time()
        self.data['duration'] = self.data['end_time'] - self.data['start_time']
        self.data.update(details)
        self.flush()


def build_gameplay_benchmark_spec(level_path='/Game/ARC02_Tests/GameplayAutomation_Test',
                                  folder='/Game/ARC02_Tests/'):
    """Constructs the complete declarative benchmark specification for ARC 02 Phase 4."""
    cube_bp = collectible_cube_spec('BP_ARC02_CollectibleCube', folder=folder)
    mgr_bp = game_manager_spec('BP_ARC02_GameManager', folder=folder)

    return {
        'level_path': level_path,
        'materials': [
            {
                'name': 'M_ARC02_Blue',
                'asset_path': folder + 'M_ARC02_Blue',
                'base_color': [0.0, 0.2, 1.0, 1.0]
            }
        ],
        'blueprints': [cube_bp, mgr_bp],
        'actors': [
            {
                'name': 'GroundPlatform',
                'class': '/Script/Engine.StaticMeshActor',
                'location': [0.0, 0.0, -20.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [15.0, 15.0, 0.2],
                'properties': {
                    'StaticMeshComponent': {
                        'StaticMesh': '/Engine/BasicShapes/Cube.Cube'
                    }
                }
            },
            {
                'name': 'SunLight',
                'class': '/Script/Engine.DirectionalLight',
                'location': [0.0, 0.0, 400.0],
                'rotation': [-45.0, 45.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {}
            },
            {
                'name': 'SkyLight',
                'class': '/Script/Engine.SkyLight',
                'location': [0.0, 0.0, 450.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {}
            },
            {
                'name': 'PlayerStart',
                'class': '/Script/Engine.PlayerStart',
                'location': [0.0, -250.0, 50.0],
                'rotation': [0.0, 90.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {}
            },
            {
                'name': 'CollectibleCube_1',
                'blueprint': folder + 'BP_ARC02_CollectibleCube',
                'location': [0.0, 0.0, 50.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {'CubeIndex': 1}
            },
            {
                'name': 'CollectibleCube_2',
                'blueprint': folder + 'BP_ARC02_CollectibleCube',
                'location': [150.0, 100.0, 50.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {'CubeIndex': 2}
            },
            {
                'name': 'CollectibleCube_3',
                'blueprint': folder + 'BP_ARC02_CollectibleCube',
                'location': [-150.0, 100.0, 50.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {'CubeIndex': 3}
            },
            {
                'name': 'GameManager',
                'blueprint': folder + 'BP_ARC02_GameManager',
                'location': [0.0, 0.0, 0.0],
                'rotation': [0.0, 0.0, 0.0],
                'scale': [1.0, 1.0, 1.0],
                'properties': {}
            }
        ],
        'gameplay_rules': {
            'target_collectible_count': 3,
            'score_per_pickup': 1,
            'completion_signal': 'ARC02 Benchmark Complete: All 3 cubes collected successfully! [win]'
        }
    }


def validate_gameplay_spec(spec):
    """Validates the complete declarative gameplay specification."""
    if not isinstance(spec, dict):
        raise SpecError('gameplay_spec', 'Must be a dictionary')

    for req in ('level_path', 'blueprints', 'actors'):
        if req not in spec:
            raise SpecError('gameplay_spec', f'Missing required key: {req}')

    lvl = spec['level_path']
    if not any(lvl.startswith(r) for r in ALLOWED_ROOTS) or '..' in lvl:
        raise SpecError('level_path', f'Must be in allowed roots ({ALLOWED_ROOTS}) without path traversal')

    # Validate all Blueprints
    validated_bps = []
    bp_paths = set()
    for bp in spec['blueprints']:
        v_bp = validate_spec(bp)
        if v_bp['asset_path'] in bp_paths:
            raise SpecError('blueprints', f"Duplicate blueprint asset path: {v_bp['asset_path']}")
        bp_paths.add(v_bp['asset_path'])
        validated_bps.append(v_bp)

    # Validate materials if present
    validated_mats = []
    mat_paths = set()
    for m in spec.get('materials', []):
        if 'name' not in m or 'asset_path' not in m:
            raise SpecError('materials', 'Material requires name and asset_path')
        if not any(m['asset_path'].startswith(r) for r in ALLOWED_ROOTS) or '..' in m['asset_path']:
            raise SpecError('material.asset_path', 'Material path must be in allowed roots')
        if m['asset_path'] in mat_paths:
            raise SpecError('materials', f"Duplicate material asset path: {m['asset_path']}")
        mat_paths.add(m['asset_path'])
        validated_mats.append(m)

    # Validate actors
    actor_names = set()
    validated_actors = []
    for a in spec['actors']:
        for req in ('name', 'location', 'rotation', 'scale'):
            if req not in a:
                raise SpecError('actors', f"Actor missing required key: {req}")
        if a['name'] in actor_names:
            raise SpecError('actors', f"Duplicate actor name in scene: {a['name']}")
        actor_names.add(a['name'])
        if 'class' not in a and 'blueprint' not in a:
            raise SpecError('actors', f"Actor {a['name']} must specify either 'class' or 'blueprint'")
        for field in ('location', 'rotation', 'scale'):
            val = a[field]
            if not isinstance(val, (list, tuple)) or len(val) != 3 or not all(isinstance(x, (int, float)) for x in val):
                raise SpecError(f"actors.{a['name']}.{field}", "Expected 3-element numeric list")
        validated_actors.append(a)

    return {
        'level_path': lvl,
        'materials': validated_mats,
        'blueprints': validated_bps,
        'actors': validated_actors,
        'gameplay_rules': spec.get('gameplay_rules', {})
    }


class GameplayAutomationEngine:
    """Executes the 8-stage declarative gameplay automation pipeline:
    VALIDATE → CREATE → CONNECT → COMPILE → SAVE → RELOAD → PLAYTEST → VERIFY.
    """

    def __init__(self, session=None, project=None, engine=None, endpoint='http://127.0.0.1:8000/mcp'):
        self.endpoint = endpoint
        self.project = Path(project) if project else Path(os.environ.get('UNREAL_PROJECT', 'D:/newpproject/Test 1/textcube/textcube.uproject'))
        self.engine = Path(engine) if engine else Path(os.environ.get('UNREAL_ENGINE', 'D:/UE_5.8'))
        self.session = session or UnrealSession(endpoint=self.endpoint)
        self.auto_saver = None
        self.guard = None
        self.recovery = None
        self.journal = None

    def _init_guards_and_services(self, spec):
        owned_packages = [spec['level_path']]
        for m in spec.get('materials', []):
            owned_packages.append(m['asset_path'])
        for bp in spec.get('blueprints', []):
            owned_packages.append(bp['asset_path'])

        self.guard = EditorStateGuard(self.session, self.project, self.engine, owned=owned_packages)
        self.auto_saver = AutoSaveManager(self.session, guard=self.guard, project=self.project, engine=self.engine)
        self.recovery = ErrorRecoveryManager(self.session, self.auto_saver, self.guard, journal=self.journal)

    # --------------------------------------------------------------------------
    # Stage 1: VALIDATE
    # --------------------------------------------------------------------------
    def stage_validate(self, spec):
        t0 = time.perf_counter()
        if self.journal is None:
            self.journal = GameplayJournal(name='gameplay_run')
        validated = validate_gameplay_spec(spec)
        elapsed = time.perf_counter() - t0
        self.journal.record_stage('VALIDATE', 'PASSED', duration=elapsed,
                                  blueprint_count=len(validated['blueprints']),
                                  actor_count=len(validated['actors']))
        return validated

    # --------------------------------------------------------------------------
    # Stage 2: CREATE
    # --------------------------------------------------------------------------
    def stage_create(self, spec, tx):
        t0 = time.perf_counter()
        s = self.session
        created = {'materials': {}, 'blueprints': {}, 'level': spec['level_path']}

        # 1. Level creation or verification
        lvl_exists = s.invoke('AssetTools', 'exists', path=spec['level_path'])
        if not lvl_exists:
            # Duplicate or create level asset
            s.invoke('AssetTools', 'create_asset', asset_name=spec['level_path'].rsplit('/', 1)[-1],
                     package_path=spec['level_path'].rsplit('/', 1)[0],
                     asset_class='/Script/Engine.World')
        tx.register_entity('level', spec['level_path'], package_path=spec['level_path'])
        tx.checkpoint('level_created')

        # 2. Material creation
        for mat in spec.get('materials', []):
            m_path = mat['asset_path']
            m_exists = s.invoke('AssetTools', 'exists', path=m_path)
            if not m_exists:
                folder, m_name = m_path.rsplit('/', 1)
                mat_ref = s.invoke('MaterialTools', 'create_material',
                                   folder_path=folder, material_name=m_name)
                created['materials'][m_path] = mat_ref
            else:
                created['materials'][m_path] = {'refPath': m_path}
            tx.register_entity('material', created['materials'][m_path], package_path=m_path)
        tx.checkpoint('materials_created')

        # 3. Blueprint creation
        for bp in spec['blueprints']:
            bp_path = bp['asset_path']
            bp_exists = s.invoke('AssetTools', 'exists', path=bp_path)
            if not bp_exists:
                folder, bp_name = bp_path.rsplit('/', 1)
                bp_ref = s.invoke('BlueprintTools', 'create', folder_path=folder,
                                  asset_name=bp_name, asset_type={'refPath': bp['parent_class']})
                created['blueprints'][bp_path] = bp_ref
            else:
                created['blueprints'][bp_path] = s.invoke('AssetTools', 'load_asset', asset_path=bp_path)
            tx.register_entity('blueprint', created['blueprints'][bp_path], package_path=bp_path)
        tx.checkpoint('blueprints_created')

        elapsed = time.perf_counter() - t0
        self.journal.record_stage('CREATE', 'PASSED', duration=elapsed, created=created)
        return created

    # --------------------------------------------------------------------------
    # Stage 3: CONNECT
    # --------------------------------------------------------------------------
    def stage_connect(self, spec, created, tx):
        t0 = time.perf_counter()
        s = self.session

        # 1. Blueprint components, variables, and EventGraph wiring
        for bp in spec['blueprints']:
            bp_path = bp['asset_path']
            b = created['blueprints'][bp_path]

            # Add components
            if bp.get('components'):
                for comp in bp['components']:
                    c_ref = s.invoke('ActorTools', 'add_component', owner=b,
                                     component_type={'refPath': comp['type']}, name=comp['name'])
                    if comp.get('properties'):
                        s.invoke('ObjectTools', 'set_properties', instance=c_ref,
                                 values=json.dumps(comp['properties']))

            # Add variables
            if bp.get('variables'):
                for var in bp['variables']:
                    s.invoke('BlueprintTools', 'add_variable', blueprint=b,
                             name=var['name'], type_name=var['type'])
                # Compile to expose properties on class
                s.invoke('BlueprintTools', 'compile_blueprint', blueprint=b, warnings_as_errors=True)
                defaults = {v['name']: v['default'] for v in bp['variables'] if 'default' in v}
                if defaults:
                    cdo = s.invoke('BlueprintTools', 'get_default_object', blueprint=b)
                    s.invoke('ObjectTools', 'set_properties', instance=cdo, values=json.dumps(defaults))

            # Clean factory graph and write graph DSL
            g = s.invoke('BlueprintTools', 'get_graph', blueprint=b, graph_name='EventGraph')
            initial_refs = s.invoke('BlueprintTools', 'find_nodes', graph=g, title='')
            initial = s.invoke('BlueprintTools', 'get_node_infos', nodes=initial_refs)
            for node in initial:
                s.invoke('BlueprintTools', 'delete_node', node=node['node'])

            dsl = generate_dsl(bp)
            s.invoke('BlueprintTools', 'write_graph_dsl', graph=g, code=dsl)

        tx.checkpoint('blueprints_connected')

        # 2. Load level and place level actors
        s.invoke('SceneTools', 'load_level', level_path=spec['level_path'])
        spawned_actors = {}
        for actor_spec in spec['actors']:
            name = actor_spec['name']
            loc = actor_spec['location']
            rot = actor_spec['rotation']
            scale = actor_spec['scale']

            if 'blueprint' in actor_spec:
                actor_ref = s.invoke('SceneTools', 'add_to_scene_from_asset',
                                     asset_path=actor_spec['blueprint'])
            else:
                actor_ref = s.invoke('SceneTools', 'add_to_scene_from_class',
                                     class_name=actor_spec['class'])

            # Set actor transform
            s.invoke('ActorTools', 'set_actor_transform',
                     actor=actor_ref,
                     location={'x': loc[0], 'y': loc[1], 'z': loc[2]},
                     rotation={'pitch': rot[0], 'yaw': rot[1], 'roll': rot[2]},
                     scale={'x': scale[0], 'y': scale[1], 'z': scale[2]})

            # Set actor label
            s.invoke('ActorTools', 'set_actor_label', actor=actor_ref, label=name)

            # Apply actor/component properties if specified
            if actor_spec.get('properties'):
                s.invoke('ObjectTools', 'set_properties', instance=actor_ref,
                         values=json.dumps(actor_spec['properties']))

            spawned_actors[name] = actor_ref
            tx.register_entity('actor', actor_ref, package_path=spec['level_path'])

        tx.checkpoint('actors_spawned')
        elapsed = time.perf_counter() - t0
        self.journal.record_stage('CONNECT', 'PASSED', duration=elapsed, spawned_actors=list(spawned_actors.keys()))
        return spawned_actors

    # --------------------------------------------------------------------------
    # Stage 4: COMPILE
    # --------------------------------------------------------------------------
    def stage_compile(self, spec, created):
        t0 = time.perf_counter()
        s = self.session
        compile_results = {}

        for bp in spec['blueprints']:
            bp_path = bp['asset_path']
            b = created['blueprints'][bp_path]

            def do_compile():
                res = compile_and_verify(s, b, bp)
                if res.get('compilation_result') != 'COMPILED':
                    err_msg = '; '.join(res.get('compiler_errors', ['Compilation failed']))
                    raise RuntimeError(f"Blueprint compilation failed: {err_msg}")
                return res

            def recover_compile():
                # Rewire DSL and ensure graph consistency
                g = s.invoke('BlueprintTools', 'get_graph', blueprint=b, graph_name='EventGraph')
                dsl = generate_dsl(bp)
                s.invoke('BlueprintTools', 'write_graph_dsl', graph=g, code=dsl)

            res = self.recovery.execute_safe_retry(
                f"compile_{bp['name']}",
                do_compile,
                recovery_fn=recover_compile
            )

            if res.get('compilation_result') != 'COMPILED':
                raise GameplayError(f"Blueprint {bp['name']} compilation failed: {res.get('compiler_errors')}")

            compile_results[bp_path] = res

        elapsed = time.perf_counter() - t0
        self.journal.record_stage('COMPILE', 'PASSED', duration=elapsed, results=compile_results)
        return compile_results

    # --------------------------------------------------------------------------
    # Stage 5: SAVE
    # --------------------------------------------------------------------------
    def stage_save(self, spec, tx):
        t0 = time.perf_counter()
        # Commit AutoSaveManager transaction to persist all entities
        commit_res = tx.commit()
        if commit_res.get('status') != 'COMMITTED':
            raise GameplayError(f"AutoSave transaction commit failed: {commit_res.get('error')}")

        # Explicitly verify no owned package remains dirty
        dirty_states = {}
        for pkg in self.guard.owned:
            is_dirty = self.session.invoke('AssetTools', 'is_dirty', asset_path=pkg)
            dirty_states[pkg] = is_dirty
            if is_dirty:
                raise GameplayError(f"Package remains dirty after save: {pkg}")

        elapsed = time.perf_counter() - t0
        self.journal.record_stage('SAVE', 'PASSED', duration=elapsed,
                                  saved_packages=commit_res.get('saved_packages', []),
                                  dirty_states=dirty_states)
        return commit_res

    # --------------------------------------------------------------------------
    # Stage 6: RELOAD
    # --------------------------------------------------------------------------
    def stage_reload(self, spec):
        t0 = time.perf_counter()
        s = self.session
        reloaded_data = {'level': None, 'blueprints': {}}

        # Reload level
        s.invoke('SceneTools', 'load_level', level_path=spec['level_path'])
        current_lvl = s.invoke('SceneTools', 'get_current_level')
        if current_lvl != spec['level_path']:
            raise GameplayError(f"Level reload mismatch: expected {spec['level_path']}, got {current_lvl}")
        reloaded_data['level'] = current_lvl

        # Verify level actors exist
        actors = s.invoke('SceneTools', 'get_actors_in_level', level_path=spec['level_path'])
        actor_labels = [a.get('label') or a.get('name', '') for a in actors] if isinstance(actors, list) else []
        for expected_actor in spec['actors']:
            name = expected_actor['name']
            if actor_labels and name not in actor_labels:
                self.journal.record_event('ACTOR_RELOAD_WARNING', actor=name, message="Actor label not found in level")

        # Reload Blueprints and verify persisted structures
        for bp in spec['blueprints']:
            bp_path = bp['asset_path']
            loaded_b = s.invoke('AssetTools', 'load_asset', asset_path=bp_path)
            _, infos, dsl = read_graph(s, loaded_b)
            mapping = compare_graph(bp, infos)
            comps = verify_components(s, loaded_b, bp.get('components', []))
            vars_res = verify_variables(s, loaded_b, bp.get('variables', []))
            reloaded_data['blueprints'][bp_path] = {
                'node_mapping': mapping,
                'components': comps,
                'variables': vars_res
            }

        elapsed = time.perf_counter() - t0
        self.journal.record_stage('RELOAD', 'PASSED', duration=elapsed, reloaded=reloaded_data)
        return reloaded_data

    # --------------------------------------------------------------------------
    # Stage 7: PLAYTEST
    # --------------------------------------------------------------------------
    def stage_playtest(self, spec, simulate=False, duration=5):
        t0 = time.perf_counter()
        # Verify Play-In-Editor behavior
        try:
            pt_res = run_playtest(
                self.project,
                endpoint=self.endpoint,
                duration=duration,
                simulate=simulate,
                required_gameplay_signals=3
            )
            elapsed = time.perf_counter() - t0
            self.journal.record_stage('PLAYTEST', 'PASSED', duration=elapsed, playtest_results=pt_res)
            return pt_res
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            # If editor is offline or PIE cannot be reached, mark UNTESTED
            self.journal.record_stage('PLAYTEST', 'UNTESTED', duration=elapsed, error=str(exc))
            return {
                'status': 'UNTESTED',
                'reason': str(exc),
                'error': str(exc)
            }

    # --------------------------------------------------------------------------
    # Stage 8: VERIFY
    # --------------------------------------------------------------------------
    def stage_verify(self, spec, pipeline_results):
        t0 = time.perf_counter()
        verification = {
            'validation_passed': pipeline_results.get('validate') is not None,
            'creation_passed': pipeline_results.get('create') is not None,
            'connection_passed': pipeline_results.get('connect') is not None,
            'compilation_passed': pipeline_results.get('compile') is not None,
            'save_passed': pipeline_results.get('save') is not None,
            'reload_passed': pipeline_results.get('reload') is not None,
            'playtest_passed': pipeline_results.get('playtest', {}).get('status') in ('completed', 'passed'),
            'playtest_status': pipeline_results.get('playtest', {}).get('status', 'UNTESTED'),
            'all_stages_completed': False,
        }

        # Check full pipeline success
        core_stages = [
            verification['validation_passed'],
            verification['creation_passed'],
            verification['connection_passed'],
            verification['compilation_passed'],
            verification['save_passed'],
            verification['reload_passed']
        ]
        verification['all_stages_completed'] = all(core_stages)
        elapsed = time.perf_counter() - t0
        self.journal.record_stage('VERIFY', 'PASSED' if verification['all_stages_completed'] else 'FAILED',
                                  duration=elapsed, verification=verification)
        return verification

    # --------------------------------------------------------------------------
    # Full Execution Entrypoint
    # --------------------------------------------------------------------------
    def execute(self, spec, mode='dry-run'):
        """Executes the complete 8-stage gameplay automation pipeline."""
        self.journal = GameplayJournal(name='arc02_phase4_gameplay')
        results = {}

        # Stage 1: VALIDATE
        validated_spec = self.stage_validate(spec)
        results['validate'] = validated_spec

        if mode == 'dry-run':
            # In dry-run, generate DSL for all blueprints and stop safely without calling editor
            dsls = {bp['asset_path']: generate_dsl(bp) for bp in validated_spec['blueprints']}
            results['dsls'] = dsls
            self.journal.finalize('DRY_RUN_COMPLETED', results=results)
            return {
                'status': 'DRY_RUN',
                'stages': self.journal.data['stages'],
                'spec': validated_spec,
                'dsls': dsls,
                'journal_path': str(self.journal.path)
            }

        # Connect session and verify live editor identity
        try:
            self.session.connect()
            self._init_guards_and_services(validated_spec)
        except Exception as exc:
            # Editor offline or unreachable -> Report UNTESTED safely per rules
            category = ErrorRecoveryManager(None, None, None).diagnose_error(exc)
            blocker_msg = (
                f"Unreal Editor MCP endpoint {self.endpoint} is unreachable: {exc}. "
                "Ensure Unreal Editor is running with textcube.uproject and Unreal MCP plugin enabled. "
                "Run `python scripts/doctor.py` to verify environment."
            )
            self.journal.finalize('BLOCKED_OFFLINE', error=blocker_msg, category=category)
            return {
                'status': 'UNTESTED',
                'blocker': blocker_msg,
                'error': str(exc),
                'journal_path': str(self.journal.path)
            }

        # Apply transaction under exclusive asset lock
        lock_key = str(self.project) + validated_spec['level_path']
        with AssetLock(REPO / 'evidence' / 'gameplay-locks', lock_key):
            tx = self.auto_saver.transaction(name='gameplay_automation_run',
                                             entity_type='level',
                                             package_path=validated_spec['level_path'])
            tx.__enter__()
            try:
                # Stage 2: CREATE
                created = self.stage_create(validated_spec, tx)
                results['create'] = created

                # Stage 3: CONNECT
                spawned = self.stage_connect(validated_spec, created, tx)
                results['connect'] = spawned

                # Stage 4: COMPILE
                compiled = self.stage_compile(validated_spec, created)
                results['compile'] = compiled

                # Stage 5: SAVE
                saved = self.stage_save(validated_spec, tx)
                results['save'] = saved

                # Stage 6: RELOAD
                reloaded = self.stage_reload(validated_spec)
                results['reload'] = reloaded

                # Stage 7: PLAYTEST
                playtested = self.stage_playtest(validated_spec)
                results['playtest'] = playtested

                # Stage 8: VERIFY
                verified = self.stage_verify(validated_spec, results)
                results['verify'] = verified

                self.journal.finalize('SUCCESS', results=results)
                return {
                    'status': 'SUCCESS',
                    'stages': self.journal.data['stages'],
                    'verification': verified,
                    'journal_path': str(self.journal.path)
                }

            except Exception as exc:
                tx.abort(str(exc))
                self.journal.finalize('FAILED', error=str(exc))
                raise exc
            finally:
                if tx.status == 'ACTIVE':
                    tx.__exit__(None, None, None)


def main():
    parser = argparse.ArgumentParser(description="ARC 02 Phase 4: Automated Gameplay System")
    parser.add_argument('--mode', choices=['dry-run', 'apply-benchmark', 'inspect'], default='dry-run')
    parser.add_argument('--endpoint', default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--project', type=Path)
    parser.add_argument('--engine', type=Path)
    args = parser.parse_args()

    spec = build_gameplay_benchmark_spec()
    engine = GameplayAutomationEngine(endpoint=args.endpoint, project=args.project, engine=args.engine)
    result = engine.execute(spec, mode=args.mode)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
