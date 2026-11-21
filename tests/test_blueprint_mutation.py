import unittest,tempfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from blueprint_mutation import AssetLock,run
from blueprint_spec import example_spec
from blueprint_verify import compare_graph
class SafetyTests(unittest.TestCase):
 def test_lock(self):
  with tempfile.TemporaryDirectory() as d:
   with AssetLock(Path(d),'same'):
    with self.assertRaises(RuntimeError):
     with AssetLock(Path(d),'same'):pass
   with AssetLock(Path(d),'same'):pass
 def test_dry_run_never_calls_editor(self):
  class Never:
   def __getattr__(self,n):raise AssertionError(n)
  r=run(example_spec(),'dry-run',session=Never());self.assertEqual(r['status'],'DRY_RUN')
 def test_modify_existing_disabled(self):
  with self.assertRaises(ValueError):run(example_spec(),'modify-existing')
 def test_graph_mismatch(self):
  with self.assertRaises(ValueError):compare_graph(example_spec(),[])
if __name__=='__main__':unittest.main()

class GraphVerificationTests(unittest.TestCase):
 def setUp(self):
  import json
  self.infos=json.loads((Path(__file__).parent/'fixtures/phase3-native-graph.json').read_text())
 def test_real_engine_graph(self):self.assertEqual(set(compare_graph(example_spec(),self.infos)),{'begin','print'})
 def test_broken_backlink(self):
  self.infos[1]['input_pins'][0]['connected_pins']=[]
  with self.assertRaises(ValueError):compare_graph(example_spec(),self.infos)
 def test_wrong_message(self):
  self.infos[1]['input_pins'][1]['value']='wrong'
  with self.assertRaises(ValueError):compare_graph(example_spec(),self.infos)
 def test_wrong_node(self):
  self.infos[1]['type_id']='Unexpected'
  with self.assertRaises(ValueError):compare_graph(example_spec(),self.infos)
 def test_extra_node(self):
  self.infos.append(self.infos[-1])
  with self.assertRaises(ValueError):compare_graph(example_spec(),self.infos)
 def test_compile_failure(self):
  from blueprint_verify import compile_and_verify
  class Failed:
   def invoke(self,*a,**kw):raise RuntimeError('Compiler error at node X')
  r=compile_and_verify(Failed(),{'refPath':'unused'},example_spec())
  self.assertEqual(r['compilation_result'],'FAILED');self.assertIn('node X',r['compiler_errors'][0])
 def test_disconnect(self):
  from blueprint_verify import compile_and_verify
  class Offline:
   def invoke(self,*a,**kw):raise ConnectionError('Editor disconnected')
  self.assertEqual(compile_and_verify(Offline(),{},example_spec())['compilation_result'],'FAILED')
 def test_journal_durable(self):
  from unittest.mock import patch
  from blueprint_mutation import Journal
  import json
  with tempfile.TemporaryDirectory() as d,patch('blueprint_mutation.REPO',Path(d)):
   j=Journal('/Game/CodexBridgeTests/Blueprints/BP_CodexBridge_Test');j.step('write_intent');j.data['status']='FAILED';j.flush()
   data=json.loads(j.path.read_text());self.assertEqual(data['status'],'FAILED');self.assertEqual(data['save_status'],'NOT_ATTEMPTED');self.assertFalse(data['atomic'])
 def test_identity_relative_path_rejected(self):
  from unreal_session import verify_process_identity
  from bridge_mcp import MCPError
  with self.assertRaises(MCPError):verify_process_identity({'ExecutablePath':'D:/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe','CommandLine':'UnrealEditor.exe UnrealCodexTest.uproject'},Path('UnrealCodexTest.uproject'),Path('D:/UE_5.8'))
 def test_second_process_lock(self):
  import subprocess
  with tempfile.TemporaryDirectory() as d:
   with AssetLock(Path(d),'same'):
    code="from blueprint_mutation import AssetLock; from pathlib import Path\nwith AssetLock(Path("+repr(d)+"),'same'):pass"
    r=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1]/'scripts',capture_output=True,text=True)
    self.assertNotEqual(r.returncode,0);self.assertIn('Mutation lock exists',r.stderr)
