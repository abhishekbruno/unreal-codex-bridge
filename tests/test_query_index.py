import json
import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_index import ProjectIndexDB
from query_project_index import ProjectIndexQuery, format_search_markdown


class TestProjectIndexQuery(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'query_test.sqlite'
        self.db = ProjectIndexDB(str(self.db_path))

        # Seed test data
        self.db.upsert_asset('/Game/Core/BP_GameManager', 'BP_GameManager', 'Blueprint', '/Game/Core', is_blueprint=True)
        self.db.upsert_asset('/Game/Core/BP_Player', 'BP_Player', 'Blueprint', '/Game/Core', is_blueprint=True)
        self.db.upsert_asset('/Game/Materials/M_Wood', 'M_Wood', 'Material', '/Game/Materials')

        self.db.upsert_blueprint(
            asset_path='/Game/Core/BP_Player',
            name='BP_Player',
            parent_class='Character',
            graphs=['EventGraph'],
            variables=['PlayerHealth', 'Stamina', 'MoveSpeed'],
            functions=[{'name': 'TakeDamage'}, {'name': 'Respawn'}],
            dsl_summary='Player movement and combat controller',
        )

        self.db.upsert_actor(
            level_path='/Game/Maps/TestMap',
            ref_path='/Game/Maps/TestMap:PersistentLevel.Light_1',
            label='SunLight',
            class_name='DirectionalLight',
        )

        self.db.upsert_dependency('/Game/Core/BP_Player', '/Game/Materials/M_Wood', 'dependency')
        self.db.upsert_dependency('/Game/Core/BP_GameManager', '/Game/Core/BP_Player', 'referencer')

        self.query_engine = ProjectIndexQuery(str(self.db_path))

    def tearDown(self):
        self.query_engine.close()
        self.db.close()
        self.temp_dir.cleanup()

    def test_get_by_path(self):
        res = self.query_engine.get_by_path('/Game/Core/BP_Player')
        self.assertIsNotNone(res)
        self.assertEqual(res['matched_path'], '/Game/Core/BP_Player')
        self.assertEqual(res['confidence'], 1.0)
        self.assertIn('blueprint_details', res['record'])
        self.assertEqual(res['record']['blueprint_details']['parent_class'], 'Character')

        # Check relationships
        rels = res['record']['relationships']
        self.assertEqual(rels['dependencies'], ['/Game/Materials/M_Wood'])
        self.assertEqual(rels['referencers'], ['/Game/Core/BP_GameManager'])

    def test_search_by_name(self):
        # Exact vs substring
        results = self.query_engine.search_by_name('BP_Player')
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]['matched_path'], '/Game/Core/BP_Player')
        self.assertEqual(results[0]['match_reason'], 'exact_name')

    def test_search_by_class(self):
        materials = self.query_engine.search_by_class('Material')
        self.assertEqual(len(materials), 1)
        self.assertEqual(materials[0]['matched_path'], '/Game/Materials/M_Wood')

    def test_search_by_variable(self):
        results = self.query_engine.search_by_variable('PlayerHealth')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['matched_path'], '/Game/Core/BP_Player')
        self.assertIn('PlayerHealth', results[0]['record']['variables'])

    def test_search_by_function(self):
        results = self.query_engine.search_by_function('TakeDamage')
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['matched_path'], '/Game/Core/BP_Player')

    def test_search_actors(self):
        actors = self.query_engine.search_actors(label='SunLight')
        self.assertEqual(len(actors), 1)
        self.assertEqual(actors[0]['record']['label'], 'SunLight')
        self.assertEqual(actors[0]['asset_type'], 'DirectionalLight')

    def test_general_search_ranking(self):
        # Searching "PlayerHealth" should rank blueprint variable match
        res_var = self.query_engine.general_search('PlayerHealth')
        self.assertGreaterEqual(len(res_var), 1)
        self.assertEqual(res_var[0]['matched_path'], '/Game/Core/BP_Player')

        # Searching exact path should have confidence 1.0
        res_path = self.query_engine.general_search('/Game/Materials/M_Wood')
        self.assertEqual(res_path[0]['confidence'], 1.0)

    def test_format_search_markdown(self):
        results = self.query_engine.general_search('BP_Player')
        md = format_search_markdown(results, 'BP_Player')
        self.assertIn("BP_Player", md)
        self.assertIn("Direct Dependencies", md)

    def test_missing_database_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            ProjectIndexQuery("non_existent_file.sqlite")


if __name__ == '__main__':
    unittest.main()

