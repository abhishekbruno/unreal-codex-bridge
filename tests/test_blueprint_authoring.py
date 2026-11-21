import sys, unittest, copy
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))

from blueprint_spec import validate_spec, SpecError, example_spec, test_cube_spec
from blueprint_codegen import generate_dsl
from blueprint_parser import tokenize_dsl, parse_sexpr


class SpecTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_spec(example_spec())['parent_class'], '/Script/Engine.Actor')

    def test_valid_cube_spec(self):
        spec = validate_spec(test_cube_spec())
        self.assertEqual(spec['name'], 'BP_ARC02_TestCube')
        self.assertEqual(len(spec['components']), 1)
        self.assertEqual(len(spec['variables']), 1)
        self.assertEqual(spec['components'][0]['name'], 'CubeMesh')
        self.assertEqual(spec['variables'][0]['name'], 'TestScore')

    def reject(self, edit):
        s = example_spec()
        edit(s)
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_protected_path(self):
        self.reject(lambda s: s.update(asset_path='/Game/User/BP_Test'))

    def test_traversal(self):
        self.reject(lambda s: s.update(asset_path='/Game/CodexBridgeTests/Blueprints/../BP_Test'))

    def test_parent(self):
        self.reject(lambda s: s.update(parent_class='/Script/Engine.Pawn'))

    def test_unknown(self):
        self.reject(lambda s: s.update(python='print(1)'))

    def test_duplicate(self):
        self.reject(lambda s: s['graphs'][0]['nodes'].append(copy.deepcopy(s['graphs'][0]['nodes'][0])))

    def test_missing_node(self):
        self.reject(lambda s: s['graphs'][0]['connections'][0]['to'].update(node='missing'))

    def test_missing_pin(self):
        self.reject(lambda s: s['graphs'][0]['connections'][0]['to'].update(pin='missing'))

    def test_wrong_direction(self):
        self.reject(lambda s: s['graphs'][0]['connections'][0]['to'].update(pin='then'))

    def test_wrong_type(self):
        self.reject(lambda s: s['graphs'][0]['connections'][0]['to'].update(pin='InString'))

    def test_unsupported(self):
        self.reject(lambda s: s['graphs'][0]['nodes'][1].update(type='ExecutePython'))

    def test_disconnected(self):
        self.reject(lambda s: s['graphs'][0].update(connections=[]))

    def test_bound(self):
        self.reject(lambda s: s['graphs'][0]['nodes'][1]['defaults'].update(InString='x' * 4097))

    def test_raw_dsl(self):
        self.reject(lambda s: s['graphs'][0]['nodes'][1].update(code='(evil)'))

    def test_invalid_component_type(self):
        s = test_cube_spec()
        s['components'][0]['type'] = '/Script/Engine.Actor'
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_duplicate_component_name(self):
        s = test_cube_spec()
        s['components'].append(copy.deepcopy(s['components'][0]))
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_invalid_variable_type(self):
        s = test_cube_spec()
        s['variables'][0]['type'] = 'UnrealScript'
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_duplicate_variable_name(self):
        s = test_cube_spec()
        s['variables'].append(copy.deepcopy(s['variables'][0]))
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_invalid_variable_default(self):
        s = test_cube_spec()
        s['variables'][0]['default'] = 'not an int'
        with self.assertRaises(SpecError):
            validate_spec(s)

    def test_deterministic(self):
        s = example_spec()
        self.assertEqual(generate_dsl(s), generate_dsl(copy.deepcopy(s)))

    def test_roundtrip_escaping(self):
        s = example_spec()
        msg = 'semicolon; "quote" \\path\nnewline'
        s['graphs'][0]['nodes'][1]['defaults']['InString'] = msg
        ast = parse_sexpr(tokenize_dsl(generate_dsl(s), strict=True), strict=True)
        self.assertEqual(ast[0][3][2], msg)

    def test_unbalanced(self):
        with self.assertRaises(ValueError):
            parse_sexpr(tokenize_dsl('(event E', strict=True), strict=True)

    def test_unterminated(self):
        with self.assertRaises(ValueError):
            tokenize_dsl('"broken', strict=True)


if __name__ == '__main__':
    unittest.main()
