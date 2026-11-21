import sys, unittest, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from blueprint_spec import validate_spec, SpecError, example_spec
from blueprint_codegen import generate_dsl
from blueprint_parser import tokenize_dsl, parse_sexpr

class SpecTests(unittest.TestCase):
 def test_valid(self): self.assertEqual(validate_spec(example_spec())['parent_class'],'/Script/Engine.Actor')
 def reject(self,edit):
  s=example_spec(); edit(s)
  with self.assertRaises(SpecError): validate_spec(s)
 def test_protected_path(self): self.reject(lambda s:s.update(asset_path='/Game/User/BP_Test'))
 def test_traversal(self): self.reject(lambda s:s.update(asset_path='/Game/CodexBridgeTests/Blueprints/../BP_Test'))
 def test_parent(self): self.reject(lambda s:s.update(parent_class='/Script/Engine.Pawn'))
 def test_unknown(self): self.reject(lambda s:s.update(python='print(1)'))
 def test_duplicate(self): self.reject(lambda s:s['graphs'][0]['nodes'].append(copy.deepcopy(s['graphs'][0]['nodes'][0])))
 def test_missing_node(self): self.reject(lambda s:s['graphs'][0]['connections'][0]['to'].update(node='missing'))
 def test_missing_pin(self): self.reject(lambda s:s['graphs'][0]['connections'][0]['to'].update(pin='missing'))
 def test_wrong_direction(self): self.reject(lambda s:s['graphs'][0]['connections'][0]['to'].update(pin='then'))
 def test_wrong_type(self): self.reject(lambda s:s['graphs'][0]['connections'][0]['to'].update(pin='InString'))
 def test_unsupported(self): self.reject(lambda s:s['graphs'][0]['nodes'][1].update(type='ExecutePython'))
 def test_disconnected(self): self.reject(lambda s:s['graphs'][0].update(connections=[]))
 def test_bound(self): self.reject(lambda s:s['graphs'][0]['nodes'][1]['defaults'].update(InString='x'*4097))
 def test_raw_dsl(self): self.reject(lambda s:s['graphs'][0]['nodes'][1].update(code='(evil)'))
 def test_deterministic(self):
  s=example_spec(); self.assertEqual(generate_dsl(s),generate_dsl(copy.deepcopy(s)))
 def test_roundtrip_escaping(self):
  s=example_spec();msg='semicolon; "quote" \\path\nnewline';s['graphs'][0]['nodes'][1]['defaults']['InString']=msg
  ast=parse_sexpr(tokenize_dsl(generate_dsl(s),strict=True),strict=True)
  self.assertEqual(ast[0][3][2],msg)
 def test_unbalanced(self):
  with self.assertRaises(ValueError):parse_sexpr(tokenize_dsl('(event E',strict=True),strict=True)
 def test_unterminated(self):
  with self.assertRaises(ValueError):tokenize_dsl('"broken',strict=True)

if __name__=='__main__':unittest.main()
