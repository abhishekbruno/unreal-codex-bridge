"""Unit and regression tests for ARC 02 Phase 4 Gameplay Automation Engine."""

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

from blueprint_spec import SpecError, collectible_cube_spec, game_manager_spec
from gameplay_automation import (
    build_gameplay_benchmark_spec,
    validate_gameplay_spec,
    GameplayAutomationEngine,
    ErrorRecoveryManager,
    ErrorCategory,
    GameplayError
)
from bridge_mcp import MCPError
from playtest import PIEState


def make_mock_node_infos(spec):
    from blueprint_spec import ordered_chains
    chains = ordered_chains(spec)
    infos = []
    for chain in chains:
        for idx, n in enumerate(chain):
            ref = f"/Game/ARC02_Tests/{n['id']}"
            inp = []
            if idx > 0:
                prev_id = chain[idx - 1]['id']
                pin_id = {'direction': 'EGPD_Input', 'index_id': 0, 'node': {'refPath': ref}}
                prev_out_pin = {'direction': 'EGPD_Output', 'index_id': 0, 'node': {'refPath': f"/Game/ARC02_Tests/{prev_id}"}}
                inp.append({'name': 'execute', 'direction': 'EGPD_Input', 'pin_id': pin_id, 'connected_pins': [prev_out_pin]})
            for k, v in n.get('defaults', {}).items():
                inp.append({'name': k, 'value': v, 'connected_pins': []})

            out = []
            if idx < len(chain) - 1:
                next_id = chain[idx + 1]['id']
                next_ref = f"/Game/ARC02_Tests/{next_id}"
                pin_id = {'direction': 'EGPD_Output', 'index_id': 0, 'node': {'refPath': ref}}
                next_in_pin = {'direction': 'EGPD_Input', 'index_id': 0, 'node': {'refPath': next_ref}}
                out.append({'name': 'then', 'direction': 'EGPD_Output', 'pin_id': pin_id,
                            'connected_pins': [next_in_pin]})
            else:
                pin_id = {'direction': 'EGPD_Output', 'index_id': 0, 'node': {'refPath': ref}}
                out.append({'name': 'then', 'direction': 'EGPD_Output', 'pin_id': pin_id, 'connected_pins': []})

            infos.append({
                'node': {'refPath': ref},
                'type_id': n['type'],
                'input_pins': inp,
                'output_pins': out,
            })
    return infos


class MockSession:
    """Mock UnrealSession supporting the 8-stage pipeline tools."""

    def __init__(self, fail_compile=False, fail_save=False, dirty_conflict=False):
        self.fail_compile = fail_compile
        self.fail_save = fail_save
        self.dirty_conflict = dirty_conflict
        self.compile_attempts = 0
        self.active_level = '/Game/ARC02_Tests/GameplayAutomation_Test'
        self.dirty_packages = {}
        self.created_assets = set()
        self.spawned_actors = []
        self.current_bp = ''
        self.calls = []

    def verify_identity(self, project, engine):
        return {
            'verified': True,
            'mcp_log_entries': ['Engine Version: 5.8.4', 'Project: textcube']
        }

    def load_toolset(self, ts):
        return True

    def invoke(self, toolset, tool, **kwargs):
        self.calls.append((toolset, tool, kwargs))

        if tool == 'IsPIERunning':
            return False

        if tool == 'get_current_level':
            return self.active_level

        if tool == 'exists':
            return kwargs.get('path') in self.created_assets

        if tool == 'is_dirty':
            return self.dirty_packages.get(kwargs.get('asset_path'), False)

        if tool == 'create_asset':
            pkg = f"{kwargs['package_path']}/{kwargs['asset_name']}"
            self.created_assets.add(pkg)
            self.dirty_packages[pkg] = True
            return {'refPath': pkg}

        if tool == 'create_material':
            pkg = f"{kwargs['folder_path']}/{kwargs['material_name']}"
            self.created_assets.add(pkg)
            self.dirty_packages[pkg] = True
            return {'refPath': pkg}

        if tool == 'create':
            pkg = f"{kwargs['folder_path']}/{kwargs['asset_name']}"
            self.created_assets.add(pkg)
            self.dirty_packages[pkg] = True
            return {'refPath': f"{pkg}.{kwargs['asset_name']}"}

        if tool == 'load_asset':
            return {'refPath': kwargs.get('asset_path')}

        if tool == 'get_parent':
            return {'refPath': '/Script/Engine.Actor'}

        if tool == 'add_component':
            c_name = kwargs.get('name', 'Comp')
            return {'refPath': f"{kwargs.get('owner', {}).get('refPath', '')}:{c_name}"}

        if tool == 'set_properties':
            return True

        if tool == 'add_variable':
            return True

        if tool == 'compile_blueprint':
            self.compile_attempts += 1
            bp_ref = kwargs.get('blueprint', {})
            self.current_bp = bp_ref.get('refPath', '') if isinstance(bp_ref, dict) else str(bp_ref)
            if self.fail_compile and self.compile_attempts == 1:
                raise RuntimeError("Simulated transient pin error on node print_ready")
            return {'status': 'COMPILED', 'errors': []}

        if tool == 'get_default_object':
            return {'refPath': '/Game/ARC02_Tests/Default__BP_C'}

        if tool == 'get_graph':
            bp_ref = kwargs.get('blueprint', {})
            self.current_bp = bp_ref.get('refPath', '') if isinstance(bp_ref, dict) else str(bp_ref)
            return {'refPath': '/Game/ARC02_Tests/BP.EventGraph'}

        if tool == 'find_nodes':
            spec = game_manager_spec() if 'GameManager' in self.current_bp else collectible_cube_spec()
            infos = make_mock_node_infos(spec)
            return [n['node'] for n in infos]

        if tool == 'get_node_infos':
            spec = game_manager_spec() if 'GameManager' in self.current_bp else collectible_cube_spec()
            return make_mock_node_infos(spec)

        if tool == 'delete_node':
            return True

        if tool == 'write_graph_dsl':
            return True

        if tool == 'read_graph_dsl':
            return '(event EventBeginPlay ()\n  (Development|PrintString :InString "ARC02 Collectible Cube Ready [pickup]")\n)\n'

        if tool == 'get_class':
            return {'refPath': '/Script/Engine.BlueprintGeneratedClass'}

        if tool == 'get_properties':
            return json.dumps({
                'StaticMesh': {'refPath': '/Engine/BasicShapes/Cube.Cube'},
                'CollisionProfileName': 'OverlapAllDynamic',
                'RotationRate': {'Pitch': 0.0, 'Yaw': 90.0, 'Roll': 0.0},
                'ScoreValue': 1,
                'IsCollected': False,
                'CubeIndex': 0,
                'CurrentScore': 0,
                'TargetScore': 3
            })

        if tool == 'list_variables':
            return ['ScoreValue', 'IsCollected', 'CubeIndex', 'CurrentScore', 'TargetScore']

        if tool == 'get_components':
            return [
                {'refPath': '/Game/ARC02_Tests/BP.BP_C:CubeMesh_GEN_VARIABLE'},
                {'refPath': '/Game/ARC02_Tests/BP.BP_C:RotatingMovement_GEN_VARIABLE'}
            ]

        if tool == 'save_assets':
            if self.fail_save:
                return False
            for p in kwargs.get('asset_paths', []):
                self.dirty_packages[p] = False
            return True

        if tool == 'load_level':
            lvl = kwargs.get('level_path')
            if self.dirty_conflict and self.dirty_packages.get(self.active_level):
                raise MCPError(f"Cannot load '{lvl}': the level has unsaved changes.")
            self.active_level = lvl
            return True

        if tool in ('add_to_scene_from_asset', 'add_to_scene_from_class'):
            ref = {'refPath': f"{self.active_level}:PersistentLevel.Actor_{len(self.spawned_actors)}"}
            self.spawned_actors.append(ref)
            self.dirty_packages[self.active_level] = True
            return ref

        if tool in ('set_actor_transform', 'set_actor_label'):
            return True

        if tool == 'get_actors_in_level':
            return [
                {'label': 'GroundPlatform', 'class': '/Script/Engine.StaticMeshActor'},
                {'label': 'SunLight', 'class': '/Script/Engine.DirectionalLight'},
                {'label': 'SkyLight', 'class': '/Script/Engine.SkyLight'},
                {'label': 'PlayerStart', 'class': '/Script/Engine.PlayerStart'},
                {'label': 'CollectibleCube_1', 'class': 'BP_ARC02_CollectibleCube_C'},
                {'label': 'CollectibleCube_2', 'class': 'BP_ARC02_CollectibleCube_C'},
                {'label': 'CollectibleCube_3', 'class': 'BP_ARC02_CollectibleCube_C'},
                {'label': 'GameManager', 'class': 'BP_ARC02_GameManager_C'}
            ]

        return True


class GameplaySpecValidationTests(unittest.TestCase):
    def test_benchmark_spec_structure(self):
        spec = build_gameplay_benchmark_spec()
        validated = validate_gameplay_spec(spec)
        self.assertEqual(validated['level_path'], '/Game/ARC02_Tests/GameplayAutomation_Test')
        self.assertEqual(len(validated['blueprints']), 2)
        self.assertEqual(len(validated['materials']), 1)
        self.assertEqual(len(validated['actors']), 8)
        self.assertEqual(validated['gameplay_rules']['target_collectible_count'], 3)

    def test_reject_unauthorized_level_path(self):
        spec = build_gameplay_benchmark_spec()
        spec['level_path'] = '/Game/Production/MyLevel'
        with self.assertRaises(SpecError):
            validate_gameplay_spec(spec)

    def test_reject_path_traversal_level(self):
        spec = build_gameplay_benchmark_spec()
        spec['level_path'] = '/Game/ARC02_Tests/../Escaped'
        with self.assertRaises(SpecError):
            validate_gameplay_spec(spec)

    def test_reject_duplicate_blueprint_path(self):
        spec = build_gameplay_benchmark_spec()
        dup_bp = copy.deepcopy(spec['blueprints'][0])
        spec['blueprints'].append(dup_bp)
        with self.assertRaises(SpecError):
            validate_gameplay_spec(spec)

    def test_reject_duplicate_actor_name(self):
        spec = build_gameplay_benchmark_spec()
        dup_actor = copy.deepcopy(spec['actors'][0])
        spec['actors'].append(dup_actor)
        with self.assertRaises(SpecError):
            validate_gameplay_spec(spec)

    def test_reject_invalid_actor_transform(self):
        spec = build_gameplay_benchmark_spec()
        spec['actors'][0]['location'] = 'not-a-list'
        with self.assertRaises(SpecError):
            validate_gameplay_spec(spec)


class ErrorRecoveryTests(unittest.TestCase):
    def test_error_diagnosis(self):
        recovery = ErrorRecoveryManager(None, None, None)
        self.assertEqual(
            recovery.diagnose_error(ConnectionRefusedError("[WinError 10061] No connection")),
            ErrorCategory.OFFLINE_DISCONNECTED
        )
        self.assertEqual(
            recovery.diagnose_error(RuntimeError("Cannot load: level has unsaved changes")),
            ErrorCategory.DIRTY_LEVEL_CONFLICT
        )
        self.assertEqual(
            recovery.diagnose_error(ValueError("Asset already exists at /Game/")),
            ErrorCategory.DUPLICATE_ASSET
        )
        self.assertEqual(
            recovery.diagnose_error(RuntimeError("Compiler error at pin direction mismatch")),
            ErrorCategory.PIN_MISMATCH
        )

    def test_safe_retry_success(self):
        recovery = ErrorRecoveryManager(None, None, None)
        attempts = 0

        def flaky_op():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("compiler failure")
            return "SUCCESS"

        result = recovery.execute_safe_retry("test_op", flaky_op, max_attempts=2)
        self.assertEqual(result, "SUCCESS")
        self.assertEqual(attempts, 2)

    def test_safe_retry_exhausted_raises(self):
        recovery = ErrorRecoveryManager(None, None, None)

        def always_fails():
            raise RuntimeError("permanent compiler error")

        with self.assertRaises(RuntimeError):
            recovery.execute_safe_retry("test_fail", always_fails, max_attempts=2)


class PipelineExecutionTests(unittest.TestCase):
    def test_dry_run_pipeline(self):
        spec = build_gameplay_benchmark_spec()
        engine = GameplayAutomationEngine()
        result = engine.execute(spec, mode='dry-run')
        self.assertEqual(result['status'], 'DRY_RUN')
        self.assertIn('VALIDATE', result['stages'])
        self.assertIn('/Game/ARC02_Tests/BP_ARC02_CollectibleCube', result['dsls'])
        self.assertIn('/Game/ARC02_Tests/BP_ARC02_GameManager', result['dsls'])

    def test_offline_editor_reports_untested(self):
        spec = build_gameplay_benchmark_spec()
        engine = GameplayAutomationEngine(endpoint='http://127.0.0.1:9999/mcp')
        result = engine.execute(spec, mode='apply-benchmark')
        self.assertEqual(result['status'], 'UNTESTED')
        self.assertIn('blocker', result)
        self.assertIn('doctor.py', result['blocker'])

    def test_full_pipeline_mock_session(self):
        spec = build_gameplay_benchmark_spec()
        session = MockSession()
        engine = GameplayAutomationEngine(session=session)

        # Mock playtest to return clean passing result
        with patch('gameplay_automation.run_playtest') as mock_pt:
            mock_pt.return_value = {
                'status': 'completed',
                'pie_state': PIEState.STOPPED,
                'evaluation': {'clean_run': True, 'gameplay_signals_found': 3}
            }

            # Execute all 8 stages
            from gameplay_automation import GameplayJournal
            engine.journal = GameplayJournal()
            engine._init_guards_and_services(spec)

            # Stage 1: VALIDATE
            v_spec = engine.stage_validate(spec)
            self.assertEqual(v_spec['level_path'], spec['level_path'])

            # Stage 2: CREATE
            tx = engine.auto_saver.transaction(name='test_tx', entity_type='level',
                                               package_path=spec['level_path'])
            tx.__enter__()
            created = engine.stage_create(v_spec, tx)
            self.assertIn(spec['level_path'], created['level'])
            self.assertEqual(len(created['blueprints']), 2)

            # Stage 3: CONNECT
            spawned = engine.stage_connect(v_spec, created, tx)
            self.assertEqual(len(spawned), 8)
            self.assertIn('CollectibleCube_1', spawned)
            self.assertIn('GroundPlatform', spawned)

            # Stage 4: COMPILE
            compiled = engine.stage_compile(v_spec, created)
            self.assertEqual(len(compiled), 2)

            # Stage 5: SAVE
            saved = engine.stage_save(v_spec, tx)
            self.assertEqual(saved['status'], 'COMMITTED')

            # Stage 6: RELOAD
            reloaded = engine.stage_reload(v_spec)
            self.assertEqual(reloaded['level'], spec['level_path'])
            self.assertEqual(len(reloaded['blueprints']), 2)

            # Stage 7: PLAYTEST
            pt = engine.stage_playtest(v_spec)
            self.assertEqual(pt['status'], 'completed')

            # Stage 8: VERIFY
            res_dict = {
                'validate': v_spec,
                'create': created,
                'connect': spawned,
                'compile': compiled,
                'save': saved,
                'reload': reloaded,
                'playtest': pt
            }
            verification = engine.stage_verify(v_spec, res_dict)
            self.assertTrue(verification['all_stages_completed'])
            self.assertTrue(verification['save_passed'])
            self.assertTrue(verification['reload_passed'])

    def test_pipeline_compiler_error_recovery(self):
        spec = build_gameplay_benchmark_spec()
        # Mock session with transient compile failure on first attempt
        session = MockSession(fail_compile=True)
        engine = GameplayAutomationEngine(session=session)
        engine._init_guards_and_services(spec)

        created = {
            'blueprints': {
                bp['asset_path']: {'refPath': bp['asset_path']}
                for bp in spec['blueprints']
            }
        }

        from gameplay_automation import GameplayJournal
        engine.journal = GameplayJournal()
        compiled = engine.stage_compile(spec, created)
        self.assertEqual(len(compiled), 2)
        # Verify it retried and recovered
        self.assertEqual(session.compile_attempts, 3)  # 1st bp: attempt 1 failed, attempt 2 passed; 2nd bp: attempt 1 passed


if __name__ == '__main__':
    unittest.main()
