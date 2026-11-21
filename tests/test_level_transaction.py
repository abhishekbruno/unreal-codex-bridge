import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from editor_state_guard import EditorStateGuard
from level_transaction import LevelTransaction
from bridge_mcp import MCPError
class Fake:
 def __init__(self):self.active='/Game/Test';self.dirty={'/Game/Test':True};self.calls=[];self.fail_save=False;self.pie=False
 def verify_identity(self,*a):return {'verified':True}
 def invoke(self,t,n,**k):
  self.calls.append((n,k))
  if n=='IsPIERunning':return self.pie
  if n=='get_current_level':return self.active
  if n=='exists':return k['path'] in self.dirty
  if n=='is_dirty':return self.dirty[k['asset_path']]
  if n=='save_assets':
   if self.fail_save:return False
   for p in k['asset_paths']:self.dirty[p]=False
   return True
  if n=='load_level':self.active=k['level_path']
class Tests(unittest.TestCase):
 def guard(self,s,project='/tmp/test.uproject'):return EditorStateGuard(s,project,'/engine',{'/Game/Test'})
 def test_dirty_owned_saved(self):
  s=Fake();self.guard(s).transition('/Game/Test',True);self.assertFalse(s.dirty['/Game/Test'])
 def test_unrelated_blocked(self):
  s=Fake();s.active='/Temp/Untitled';s.dirty[s.active]=True
  with self.assertRaises(MCPError):self.guard(s).transition('/Game/Test',True)
  self.assertFalse(any(n=='save_assets' for n,k in s.calls))
 def test_save_failure(self):
  s=Fake();s.fail_save=True
  with self.assertRaises(MCPError):self.guard(s).save('/Game/Test')
 def test_pie(self):
  s=Fake();s.pie=True
  with self.assertRaises(MCPError):self.guard(s).inspect('/Game/Test')
 def test_identity_mismatch(self):
  s=Fake()
  def fail(*a):raise MCPError('mismatch')
  s.verify_identity=fail
  with self.assertRaises(MCPError):self.guard(s).save('/Game/Test')
  self.assertEqual(s.calls,[])
 def test_incomplete_world_blocked(self):
  with self.assertRaises(MCPError):self.guard(Fake()).transition('/Game/Test')
 def test_platform_paths_delegated(self):
  for p in ('C:/Projects/test.uproject','/Users/test/test.uproject'):
   self.assertEqual(self.guard(Fake(),p).inspect('/Game/Test')['identity'],{'verified':True})
 def test_sequence_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   s=Fake();done=[]
   tx=LevelTransaction(s,'/project/test.uproject','/engine','/Game/Test',Path(d)/'journal.json',{'/Game/Test'},True)
   tx.run('/Engine/Template',lambda:done.append(True),lambda:bool(done));tx.run('/Engine/Template',lambda:done.append(True),lambda:bool(done))
   self.assertEqual(done,[True]);names=[n for n,k in s.calls];self.assertLess(names.index('save_assets'),names.index('load_level'))
 def test_interrupted_execute_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   tx=LevelTransaction(Fake(),'/project/test.uproject','/engine','/Game/Test',Path(d)/'j.json',{'/Game/Test'},True);tx.record('EXECUTE_INTENT')
   with self.assertRaises(MCPError):tx.run('/Engine/Template',lambda:self.fail('must not retry'),lambda:False)
