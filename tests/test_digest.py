import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_index import ProjectIndexDB
from generate_project_digest import ProjectDigestGenerator


class TestProjectDigest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'digest_test.sqlite'
        self.db = ProjectIndexDB(str(self.db_path))

        # Seed minimal data
        self.db.set_meta('project_name', 'TestGame')
        self.db.set_meta('engine_path', 'D:/UE_5.8')
        self.db.set_meta('active_level', '/Game/Maps/MainLevel')

        self.db.upsert_asset('/Game/BP_Char', 'BP_Char', 'Blueprint', '/Game', is_blueprint=True)
        self.db.upsert_asset('/Game/M_Base', 'M_Base', 'Material', '/Game')

        self.db.upsert_blueprint(
            asset_path='/Game/BP_Char',
            name='BP_Char',
            parent_class='Character',
            graphs=['EventGraph'],
            variables=['Health', 'Speed'],
            functions=[{'name': 'Jump'}],
            dsl_summary='Base character movement',
        )

        self.db.upsert_actor(
            level_path='/Game/Maps/MainLevel',
            ref_path='/Game/Maps/MainLevel:PersistentLevel.Cube_1',
            label='FloorCube',
            class_name='StaticMeshActor',
        )

        self.db.upsert_dependency('/Game/BP_Char', '/Game/M_Base', 'dependency')

        self.generator = ProjectDigestGenerator(str(self.db_path))

    def tearDown(self):
        self.generator.close()
        self.db.close()
        self.temp_dir.cleanup()

    def test_digest_contains_required_sections(self):
        digest = self.generator.generate_digest(budget_chars=10000, compact=False)
        self.assertIn("TestGame", digest)
        self.assertIn("Asset Inventory Overview", digest)
        self.assertIn("Core Blueprint Systems", digest)
        self.assertIn("Critical Dependency Hubs", digest)
        self.assertIn("Active Scene Outliner Summary", digest)
        self.assertIn("Index Quality & Coverage", digest)
        self.assertIn("Recommended Next Inspection Targets", digest)

    def test_compact_mode(self):
        full_digest = self.generator.generate_digest(compact=False)
        compact_digest = self.generator.generate_digest(compact=True)
        self.assertLess(len(compact_digest), len(full_digest))
        self.assertNotIn("Key Blueprint APIs & State Definitions", compact_digest)

    def test_budget_enforcement(self):
        small_digest = self.generator.generate_digest(budget_chars=400)
        self.assertLessEqual(len(small_digest), 450)
        self.assertIn("truncated to meet configured context budget", small_digest)

    def test_missing_database_raises_error(self):
        with self.assertRaises(FileNotFoundError):
            ProjectDigestGenerator("non_existent_db.sqlite")


if __name__ == '__main__':
    unittest.main()

