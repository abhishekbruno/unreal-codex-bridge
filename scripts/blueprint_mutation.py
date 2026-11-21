"""Guarded creation of isolated test Blueprints through the native MCP session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import uuid
from blueprint_spec import validate_spec, example_spec, PINS
from blueprint_codegen import generate_dsl
from blueprint_verify import compare_graph, read_graph, compile_and_verify
from unreal_session import UnrealSession

REPO=Path(__file__).resolve().parents[1]
PROJECT=Path('D:/newpproject/UnrealCodexTest/UnrealCodexTest.uproject')
ENGINE=Path('D:/UE_5.8')

class AssetLock:
 """Exclusive cross-process lock. Stale locks require manual investigation."""
 def __init__(self,directory,key):
  self.path=Path(directory)/(hashlib.sha256(key.casefold().encode()).hexdigest()+'.lock')
 def __enter__(self):
  self.path.parent.mkdir(parents=True,exist_ok=True)
  try:self.fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
  except FileExistsError:raise RuntimeError('Mutation lock exists; inspect owner/journal before manual recovery')
  os.write(self.fd,json.dumps({'pid':os.getpid(),'started':time.time()}).encode());os.fsync(self.fd)
  return self
 def __exit__(self,*args):
  os.close(self.fd);self.path.unlink()

class Journal:
 def __init__(self,asset):
  folder=REPO/'evidence'/'blueprint-mutations';folder.mkdir(parents=True,exist_ok=True)
  self.path=folder/(time.strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex+'.json')
  self.data={'asset_path':asset,'status':'STARTED','steps':[],'save_status':'NOT_ATTEMPTED','reload_verification':False,'runtime_verification':False,'atomic':False,'rollback_attempted':False}
  self.flush()
 def flush(self):
  temp=self.path.with_suffix('.tmp')
  with open(temp,'w',encoding='utf8') as f:json.dump(self.data,f,indent=2,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(temp,self.path)
 def step(self,stage,**details):
  self.data['steps'].append({'stage':stage,'time':time.time(),**details});self.flush()

def identity(session):
 info=session.verify_identity(PROJECT,ENGINE)
 if not any('Engine Version: 5.8.4-' in line for line in info['mcp_log_entries']):raise ValueError('Exact UE 5.8.4 identity required')
 return info

def run(spec,mode='dry-run',session=None):
 if mode not in ('inspect','dry-run','apply-test'):raise ValueError('Existing asset modification is disabled')
 start=time.perf_counter();spec=validate_spec(spec);validation=time.perf_counter()-start
 start=time.perf_counter();dsl=generate_dsl(spec);generation=time.perf_counter()-start
 result={'asset_path':spec['asset_path'],'dsl':dsl,'timings':{'validation':validation,'generation':generation}}
 if mode=='dry-run':return dict(result,status='DRY_RUN',editor_calls=0)
 s=session or UnrealSession();s.connect();identity(s);s.load_toolset('BlueprintTools')
 if mode=='inspect':
  b=s.invoke('AssetTools','load_asset',asset_path=spec['asset_path'])
  g=s.invoke('BlueprintTools','get_graph',blueprint=b,graph_name='EventGraph')
  refs=s.invoke('BlueprintTools','find_nodes',graph=g,title='')
  infos=s.invoke('BlueprintTools','get_node_infos',nodes=refs)
  return dict(result,status='INSPECTED',node_mapping=compare_graph(spec,infos))
 journal=Journal(spec['asset_path']);journal.data.update(result)
 with AssetLock(REPO/'evidence'/'blueprint-locks',str(PROJECT)+spec['asset_path']):
  try:
   journal.data['identity']=identity(s)
   # Retrieve schemas and native DSL reference before any creation.
   for tool in ('create','get_parent','get_graph','write_graph_dsl','compile_blueprint','find_node_types','get_node_type_pins','get_node_infos','set_node_position'):
    s.tool('BlueprintTools',tool)
   s.invoke('BlueprintTools','get_graph_dsl_docs')
   exists=s.invoke('AssetTools','exists',path=spec['asset_path']);journal.step('preflight',original_exists=exists)
   if exists is not False:raise ValueError('Asset exists or existence is uncertain; refusing overwrite')
   identity(s);journal.step('create_intent')
   t=time.perf_counter();b=s.invoke('BlueprintTools','create',folder_path=spec['asset_path'].rsplit('/',1)[0],asset_name=spec['name'],asset_type={'refPath':spec['parent_class']})
   result['timings']['creation']=time.perf_counter()-t
   journal.data['created_asset']=b;journal.step('created',unsaved=True)
   loaded=s.invoke('AssetTools','load_asset',asset_path=spec['asset_path'])
   expected=spec['asset_path']+'.'+spec['name']
   if b!={'refPath':expected} or loaded!=b:raise ValueError('Created asset identity mismatch')
   if s.invoke('BlueprintTools','get_parent',blueprint=b)!={'refPath':spec['parent_class']}:raise ValueError('Parent mismatch')
   g=s.invoke('BlueprintTools','get_graph',blueprint=b,graph_name='EventGraph')
   for node_type,pins in PINS.items():
    found=s.invoke('BlueprintTools','find_node_types',graph=g,type_id_filter=node_type,context_pins=[])
    if node_type not in found:raise ValueError('Required native node type unavailable')
    desc=s.invoke('BlueprintTools','get_node_type_pins',graph=g,type_id=node_type)
    for name,(direction,kind) in pins.items():
     if not any(p['name']==name and p['type_id']==kind for p in desc[direction+'_pins']):raise ValueError('Native pin contract mismatch')
   initial_refs=s.invoke('BlueprintTools','find_nodes',graph=g,title='')
   initial=s.invoke('BlueprintTools','get_node_infos',nodes=initial_refs)
   allowed={'AddEvent|EventBeginPlay','AddEvent|EventTick','AddEvent|Collision|EventActorBeginOverlap'}
   if len(initial)>3 or any(n['type_id'] not in allowed or any(p['connected_pins'] for p in n['input_pins']+n['output_pins']) for n in initial):
    raise ValueError('Unexpected factory graph; refusing cleanup')
   journal.step('factory_graph',nodes=initial)
   identity(s);journal.step('factory_cleanup_intent')
   for node in initial:s.invoke('BlueprintTools','delete_node',node=node['node'])
   identity(s);journal.step('graph_write_intent')
   t=time.perf_counter();s.invoke('BlueprintTools','write_graph_dsl',graph=g,code=dsl);result['timings']['graph_application']=time.perf_counter()-t
   _,infos,readback=read_graph(s,b)
   # Position verification follows layout application to mapped nodes.
   nopos=json.loads(json.dumps(spec))
   for n in nopos['graphs'][0]['nodes']:n.pop('position',None)
   mapping=compare_graph(nopos,infos)
   for n in spec['graphs'][0]['nodes']:
    if 'position' in n:
     identity(s);s.invoke('BlueprintTools','set_node_position',node=mapping[n['id']],pos={'x':n['position'][0],'y':n['position'][1]})
   journal.step('graph_verified',mapping=mapping,readback_dsl=readback)
   identity(s);t=time.perf_counter();verification=compile_and_verify(s,b,spec);result['timings']['compile_and_verification']=time.perf_counter()-t
   journal.data['verification']=verification
   journal.data['status']='BLOCKED' if verification['compilation_result']=='STATUS_UNAVAILABLE' else 'FAILED'
   journal.data['reason']='Explicit compiler status and true reload are unavailable through discovered native narrow tools. Asset deliberately not saved.'
   journal.data['dirty']=s.invoke('AssetTools','is_dirty',asset_path=spec['asset_path'])
  except Exception as exc:
   journal.data['status']='FAILED';journal.data['error']=str(exc)
   journal.data['write_outcome_uncertain']=any(x['stage'].endswith('_intent') for x in journal.data['steps'])
  finally:
   journal.data['timings']=result['timings'];journal.data['mcp_calls']=len(s.client.transcript)
   journal.data['recovery']='No automatic rollback. Inspect this exact new asset. Do not save a failed graph. If discarded manually, verify absence/dirty state before retrying under a new name.'
   journal.data['transcript']=s.client.transcript;journal.flush()
 return dict(journal.data,journal_path=str(journal.path))

def main():
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['inspect','dry-run','apply-test'],default='dry-run');p.add_argument('--spec',type=Path)
 a=p.parse_args();spec=json.loads(a.spec.read_text(encoding='utf-8-sig')) if a.spec else example_spec('BP_CodexBridge_Test_'+uuid.uuid4().hex[:12])
 result=run(spec,a.mode)
 print(json.dumps(result,indent=2,ensure_ascii=True))
 if result['status'] in ('FAILED','BLOCKED'):raise SystemExit(2)
if __name__=='__main__':main()
