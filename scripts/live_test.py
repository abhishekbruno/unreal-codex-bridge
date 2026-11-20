"""Create a unique test map and cube through discovered native MCP tools only."""
import argparse
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from bridge_mcp import MCPError
from doctor import check_engine
from unreal_session import UnrealSession

XFORM={'location':{'x':0,'y':0,'z':150},'rotation':{'pitch':0,'yaw':0,'roll':0},'scale':{'x':1,'y':1,'z':1}}
BASE='/Game/CodexBridgeTests/ARC01_TestLevel'
MESH='/Engine/BasicShapes/Cube'
TEMPLATE='/Engine/Maps/Templates/Template_Default'


def assert_transform(actual):
    for group,values in XFORM.items():
        for key,expected in values.items():
            value=actual.get(group,{}).get(key)
            if not isinstance(value,(int,float)) or not math.isclose(value,expected,abs_tol=0.0001):
                raise MCPError(f'Transform mismatch {group}.{key}: expected {expected}, got {value}')


def choose_level(exists):
    for i in range(10000):
        candidate=BASE if i==0 else f'{BASE}_{i:03d}'
        if not exists(candidate): return candidate
    raise MCPError('No unused test level name available')


def verify_cube(session, actor):
    label=session.invoke('ActorTools','get_label',actor=actor)
    if label!='Codex_Test_Cube': raise MCPError('Cube label mismatch: '+str(label))
    transform=session.invoke('ActorTools','get_actor_transform',actor=actor)
    assert_transform(transform)
    components=session.invoke('ActorTools','get_components',actor=actor)
    mesh_values=[]
    for component in components:
        properties=session.invoke('ObjectTools','list_properties',instance=component)
        # Read the property name from live reflection; never set guessed properties.
        matches=re.findall(r'\b(static_mesh|StaticMesh|staticMesh)\b',properties)
        for prop in dict.fromkeys(matches):
            values=session.invoke('ObjectTools','get_properties',instance=component,properties=[prop])
            parsed=json.loads(values) if isinstance(values,str) else values
            mesh_values.append(parsed)
    if not any(MESH+'.Cube' in json.dumps(value) or '"'+MESH+'"' in json.dumps(value) for value in mesh_values):
        raise MCPError('Static mesh assignment could not be verified: '+json.dumps(mesh_values))
    return {'actor':actor,'label':label,'transform':transform,'mesh_properties':mesh_values}


def execute(project,engine,endpoint,output):
    session=UnrealSession(endpoint,timeout=90)
    report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'status':'FAIL','stage':'preflight','checks':[]}
    def stage(name,value=None):
        report['stage']=name
        if value is not None: report['checks'].append({'name':name,'status':'PASS','detail':value})
    def require_true(value,what):
        if value is not True: raise MCPError(what+' returned '+repr(value))
        return value
    try:
        check_engine(engine)
        stage('connect'); report['initialize']=session.connect()
        stage('identity'); report['identity']=session.verify_identity(project,engine)
        # Preflight every needed operation before any scene mutation.
        for toolset,names in {
            'SceneTools':['get_current_level','load_level','find_actors','add_to_scene_from_asset'],
            'AssetTools':['exists','is_dirty','duplicate','save_assets'],
            'ActorTools':['get_label','get_actor_transform','get_components'],
            'ObjectTools':['list_properties','get_properties'],
            'EditorAppToolset':['IsPIERunning'],
        }.items():
            for name in names: session.tool(toolset,name)
        if session.invoke('EditorAppToolset','IsPIERunning') is not False:
            raise MCPError('Stop Play-In-Editor before running the creation test')
        original=session.invoke('SceneTools','get_current_level')
        report['original_level']=original
        if not original or not session.invoke('AssetTools','exists',path=original):
            raise MCPError('Current level is unsaved or unavailable; save it manually first')
        if session.invoke('AssetTools','is_dirty',asset_path=original) is not False:
            raise MCPError('Current level has unsaved changes; save it manually before switching')
        stage('initial_actor_listing',session.invoke('SceneTools','find_actors',name='',tag='',collision_channels=[]))
        for asset in (MESH,TEMPLATE):
            require_true(session.invoke('AssetTools','exists',path=asset),'Required engine asset '+asset)
        level=choose_level(lambda path:session.invoke('AssetTools','exists',path=path))
        report['test_level']=level
        # Confirm identity again immediately before the first write.
        session.verify_identity(project,engine)
        stage('create_test_level')
        require_true(session.invoke('AssetTools','duplicate',path=TEMPLATE,new_path=level),'Duplicate template level')
        stage('create_test_level',level)
        # The native duplicate operation creates a dirty in-memory World. UE 5.8
        # load_level refuses dirty target maps, so persist this new map first.
        stage('save_new_map')
        require_true(session.invoke('AssetTools','save_assets',asset_paths=[level]),'Save newly duplicated map')
        stage('load_test_level');session.invoke('SceneTools','load_level',level_path=level)
        if session.invoke('SceneTools','get_current_level')!=level: raise MCPError('Test map did not become current')
        if session.invoke('SceneTools','find_actors',name='Codex_Test_Cube',tag='',collision_channels=[]):
            raise MCPError('Unexpected existing Codex_Test_Cube; refusing to modify it')
        stage('create_cube')
        actor=session.invoke('SceneTools','add_to_scene_from_asset',asset_path=MESH,name='Codex_Test_Cube',xform=XFORM,snap_to_ground=False)
        if not isinstance(actor,dict) or not actor.get('refPath'): raise MCPError('Actor creation returned no reference')
        report['created_actor']=actor
        stage('verify_cube');report['before_save']=verify_cube(session,actor)
        listed=session.invoke('SceneTools','find_actors',name='Codex_Test_Cube',tag='',collision_channels=[])
        if actor not in listed: raise MCPError('Created actor absent from actual actor query')
        stage('verify_cube',report['before_save'])
        stage('save_test_level')
        require_true(session.invoke('AssetTools','save_assets',asset_paths=[level]),'Save test map')
        if session.invoke('AssetTools','is_dirty',asset_path=level) is not False: raise MCPError('Map remains dirty after save')
        stage('save_test_level',True)
        report['after_save']=verify_cube(session,actor)
        stage('reload_test_level')
        session.invoke('SceneTools','load_level',level_path=original)
        if session.invoke('SceneTools','get_current_level')!=original: raise MCPError('Could not unload the test level')
        session.invoke('SceneTools','load_level',level_path=level)
        if session.invoke('SceneTools','get_current_level')!=level: raise MCPError('Could not reload the test level')
        listed=session.invoke('SceneTools','find_actors',name='Codex_Test_Cube',tag='',collision_channels=[])
        if len(listed)!=1: raise MCPError('Expected exactly one persisted cube')
        report['after_reload']=verify_cube(session,listed[0])
        saved=project.parent/'Content'/Path(level.removeprefix('/Game/')+'.umap')
        if not saved.is_file() or saved.stat().st_size==0: raise MCPError('Saved .umap file missing')
        report['saved_file']={'path':str(saved),'bytes':saved.stat().st_size}
        stage('persistence',report['after_reload'])
        report['status']='PASS';report['stage']='complete'
    except (MCPError,ValueError,OSError,KeyError,TypeError) as exc:
        report['error']=str(exc)
        # No cleanup deletion, retries of writes, or saving unrelated content.
    finally:
        report['transcript']=session.client.transcript
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--engine',type=Path,required=True)
    parser.add_argument('--endpoint',default='http://127.0.0.1:8000/mcp')
    parser.add_argument('--output',type=Path,default=Path('evidence/live-test-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json'))
    args=parser.parse_args()
    report=execute(args.project.resolve(),args.engine.resolve(),args.endpoint,args.output)
    print(json.dumps({k:v for k,v in report.items() if k not in ('transcript','checks','initialize')},indent=2))
    print('Evidence:',args.output.resolve())
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__': raise SystemExit(main())
