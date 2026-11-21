import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from project_index import CURRENT_SCHEMA_VERSION, ProjectIndexDB, normalize_package_path


class TestProjectIndexDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'test_index.sqlite'
        self.db = ProjectIndexDB(str(self.db_path))

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_schema_and_metadata_initialization(self):
        self.assertTrue(self.db_path.exists())
        version = self.db.get_meta('schema_version')
        self.assertEqual(version, str(CURRENT_SCHEMA_VERSION))

        # Check table creation
        cur = self.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {r[0] for r in cur.fetchall()}
        self.assertIn('assets', tables)
        self.assertIn('blueprints', tables)
        self.assertIn('actors', tables)
        self.assertIn('dependencies', tables)
        self.assertIn('fts_index', tables)

    def test_upsert_asset_and_fts(self):
        aid = self.db.upsert_asset(
            path='/Game/Characters/BP_Hero',
            name='BP_Hero',
            class_name='Blueprint',
            package_folder='/Game/Characters',
            is_blueprint=True,
            parent_class='/Script/Engine.Character',
            item_type='Blueprint Class',
            metadata={'Description': 'Player character controller'},
            mtime=12345.0,
        )
        self.assertTrue(bool(aid))

        # Retrieve direct record
        row = self.db.conn.execute("SELECT * FROM assets WHERE id = ?;", (aid,)).fetchone()
        self.assertEqual(row['name'], 'BP_Hero')
        self.assertEqual(row['parent_class'], '/Script/Engine.Character')
        self.assertEqual(row['is_blueprint'], 1)

        # Retrieve via FTS5
        fts_res = self.db.conn.execute(
            "SELECT entity_id, name, path FROM fts_index WHERE fts_index MATCH 'Hero';"
        ).fetchall()
        self.assertEqual(len(fts_res), 1)
        self.assertEqual(fts_res[0]['name'], 'BP_Hero')

    def test_upsert_blueprint_and_fts_elements(self):
        self.db.upsert_blueprint(
            asset_path='/Game/Blueprints/BP_Door',
            name='BP_Door',
            parent_class='Actor',
            graphs=['EventGraph', 'UserConstructionScript'],
            variables=['IsOpen', 'OpenAngle', 'KeyRequired'],
            functions=[{'name': 'OpenDoor'}, {'name': 'CloseDoor'}],
            dsl_summary='Door state machine with rotation',
        )

        row = self.db.conn.execute("SELECT * FROM blueprints WHERE asset_path = ?;",
                                   ('/Game/Blueprints/BP_Door',)).fetchone()
        self.assertEqual(row['name'], 'BP_Door')
        self.assertEqual(row['variable_count'], 3)
        self.assertEqual(row['function_count'], 2)

        # Search by variable name via FTS
        fts_var = self.db.conn.execute(
            "SELECT entity_id, name FROM fts_index WHERE fts_index MATCH 'KeyRequired';"
        ).fetchall()
        self.assertEqual(len(fts_var), 1)
        self.assertEqual(fts_var[0]['name'], 'BP_Door')

    def test_upsert_actor_and_location(self):
        aid = self.db.upsert_actor(
            level_path='/Game/Maps/MainMap',
            ref_path='/Game/Maps/MainMap:PersistentLevel.Light_1',
            label='DirectionalLight_1',
            class_name='DirectionalLight',
            transform={'location': {'x': 100.0, 'y': 200.0, 'z': 300.0}},
            components=[{'refPath': 'comp1', 'class': 'DirectionalLightComponent'}],
            tags=['Sun', 'Daylight'],
        )

        row = self.db.conn.execute("SELECT * FROM actors WHERE id = ?;", (aid,)).fetchone()
        self.assertEqual(row['label'], 'DirectionalLight_1')
        self.assertEqual(row['location_x'], 100.0)
        self.assertEqual(row['location_z'], 300.0)

    def test_dependencies_and_referencers(self):
        self.db.upsert_dependency('/Game/BP_Player', '/Game/M_PlayerMat', 'dependency')
        self.db.upsert_dependency('/Game/BP_Weapon', '/Game/BP_Player', 'referencer')

        deps = self.db.conn.execute(
            "SELECT target_path FROM dependencies WHERE source_path = ? AND relation_type = 'dependency';",
            ('/Game/BP_Player',)
        ).fetchall()
        self.assertEqual([r[0] for r in deps], ['/Game/M_PlayerMat'])

    def test_stale_asset_marking(self):
        self.db.upsert_asset('/Game/AssetA', 'AssetA', 'StaticMesh', '/Game')
        self.db.upsert_asset('/Game/AssetB', 'AssetB', 'StaticMesh', '/Game')

        # Pass 2: only AssetA is observed
        self.db.mark_stale_unseen({'/Game/AssetA'})

        row_a = self.db.conn.execute("SELECT status FROM assets WHERE path = '/Game/AssetA';").fetchone()
        row_b = self.db.conn.execute("SELECT status FROM assets WHERE path = '/Game/AssetB';").fetchone()

        self.assertEqual(row_a['status'], 'active')
        self.assertEqual(row_b['status'], 'stale')

    def test_database_stats(self):
        self.db.upsert_asset('/Game/Asset1', 'Asset1', 'Material', '/Game')
        self.db.upsert_actor('/Game/Level', '/Game/Level:Actor1', 'Actor1', 'Brush')

        stats = self.db.get_stats()
        self.assertEqual(stats['total_assets'], 1)
        self.assertEqual(stats['actors_indexed'], 1)
        self.assertGreater(stats['database_size_bytes'], 0)


if __name__ == '__main__':
    unittest.main()

