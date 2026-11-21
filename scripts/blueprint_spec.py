"""Bounded declarative Actor Blueprint subset. No user supplied DSL/code."""
import copy
import re

ROOT = '/Game/CodexBridgeTests/Blueprints/'
PINS = {
 'AddEvent|EventBeginPlay': {'then': ('output','Exec')},
 'Development|PrintString': {'execute': ('input','Exec'), 'then': ('output','Exec'), 'InString': ('input','String')},
}
class SpecError(ValueError):
 def __init__(self,path,message):
  self.errors=[{'path':path,'message':message}];super().__init__(f'{path}: {message}')

def require(ok,path,message):
 if not ok: raise SpecError(path,message)

def keys(obj,allowed,required,path):
 require(isinstance(obj,dict),path,'must be an object')
 require(set(obj)<=set(allowed),path,'unknown fields')
 require(set(required)<=set(obj),path,'missing required fields')

def validate_spec(spec):
 keys(spec,('name','parent_class','asset_path','graphs','variables'),('name','parent_class','asset_path','graphs','variables'),'spec')
 require(isinstance(spec['name'],str) and re.fullmatch(r'BP_CodexBridge_Test[A-Za-z0-9_]{0,80}',spec['name']),'name','invalid isolated test name')
 require(spec['asset_path']==ROOT+spec['name'],'asset_path','must be the exact isolated test path')
 require(spec['parent_class']=='/Script/Engine.Actor','parent_class','only Actor supported')
 require(spec['variables']==[],'variables','variable declarations are not yet supported')
 require(isinstance(spec['graphs'],list) and len(spec['graphs'])==1,'graphs','exactly one graph required')
 g=spec['graphs'][0];keys(g,('name','nodes','connections'),('name','nodes','connections'),'graph')
 require(g['name']=='EventGraph','graph.name','only EventGraph supported')
 require(isinstance(g['nodes'],list) and 2<=len(g['nodes'])<=32,'nodes','expected 2..32 nodes')
 nodes={}
 for n in g['nodes']:
  keys(n,('id','type','defaults','position'),('id','type','defaults'),'node')
  require(isinstance(n['id'],str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',n['id']),'node.id','invalid stable id')
  require(n['id'] not in nodes,'node.id','duplicate id')
  require(isinstance(n['type'],str) and n['type'] in PINS,'node.type','unsupported node')
  keys(n['defaults'],('InString',) if n['type']=='Development|PrintString' else (),('InString',) if n['type']=='Development|PrintString' else (),'defaults')
  if n['defaults']:
   v=n['defaults']['InString'];require(isinstance(v,str) and len(v)<=4096 and not any(ord(c)<32 and c not in '\n\r\t' for c in v),'InString','expected bounded text without control codes')
  if 'position' in n:
   require(isinstance(n['position'],list) and len(n['position'])==2 and all(type(v) is int and abs(v)<=100000 for v in n['position']),'position','expected two bounded integers')
  nodes[n['id']]=n
 require(sum(n['type']=='AddEvent|EventBeginPlay' for n in nodes.values())==1,'nodes','exactly one BeginPlay required')
 require(isinstance(g['connections'],list) and len(g['connections'])==len(nodes)-1,'connections','all nodes must form one execution chain')
 outgoing={}; incoming=set()
 for c in g['connections']:
  keys(c,('from','to'),('from','to'),'connection')
  pins=[]
  for side,direction in [('from','output'),('to','input')]:
   e=c[side];keys(e,('node','pin'),('node','pin'),side)
   require(isinstance(e['node'],str) and e['node'] in nodes,side,'undefined node')
   require(isinstance(e['pin'],str) and e['pin'] in PINS[nodes[e['node']]['type']],side,'undefined pin')
   p=PINS[nodes[e['node']]['type']][e['pin']];require(p[0]==direction,side,'invalid pin direction');pins.append(p)
  require(pins[0][1]==pins[1][1]=='Exec','connection','only compatible execution links supported')
  a,b=c['from']['node'],c['to']['node'];require(a not in outgoing and b not in incoming,'connection','branch or multiple inputs unsupported')
  outgoing[a]=b;incoming.add(b)
 start=next(n['id'] for n in nodes.values() if n['type']=='AddEvent|EventBeginPlay');seen=set()
 while start:
  require(start not in seen,'connections','cycle');seen.add(start);start=outgoing.get(start)
 require(seen==set(nodes),'connections','disconnected nodes')
 return copy.deepcopy(spec)

def ordered_nodes(spec):
 g=spec['graphs'][0];nodes={n['id']:n for n in g['nodes']};nexts={c['from']['node']:c['to']['node'] for c in g['connections']}
 current=next(n['id'] for n in nodes.values() if n['type']=='AddEvent|EventBeginPlay');result=[]
 while current:result.append(nodes[current]);current=nexts.get(current)
 return result

def example_spec(name='BP_CodexBridge_Test'):
 return {'name':name,'parent_class':'/Script/Engine.Actor','asset_path':ROOT+name,'variables':[], 'graphs':[{'name':'EventGraph','nodes':[{'id':'begin','type':'AddEvent|EventBeginPlay','defaults':{}},{'id':'print','type':'Development|PrintString','defaults':{'InString':'Unreal Codex Bridge: Blueprint execution successful'}}], 'connections':[{'from':{'node':'begin','pin':'then'},'to':{'node':'print','pin':'execute'}}]}]}
