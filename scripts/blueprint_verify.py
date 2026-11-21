"""Semantic graph verification; compiler evidence is deliberately explicit."""
from blueprint_spec import ordered_nodes, validate_spec

def compare_graph(spec, infos):
 expected=ordered_nodes(validate_spec(spec))
 if len(infos)!=len(expected):raise ValueError(f'Node count mismatch: {len(infos)} != {len(expected)}')
 starts=[n for n in infos if n['type_id']=='AddEvent|EventBeginPlay']
 if len(starts)!=1:raise ValueError('BeginPlay count mismatch')
 by_ref={n['node']['refPath']:n for n in infos};actual=starts[0];mapping={};seen=set()
 for index,wanted in enumerate(expected):
  ref=actual['node']['refPath']
  if ref in seen or actual['type_id']!=wanted['type']:raise ValueError('Unexpected node type or cycle')
  seen.add(ref);mapping[wanted['id']]=actual['node']
  if 'position' in wanted and actual['position']!={'x':wanted['position'][0],'y':wanted['position'][1]}:raise ValueError('Node position mismatch')
  for key,value in wanted['defaults'].items():
   pins=[p for p in actual['input_pins'] if p['name']==key]
   if len(pins)!=1 or pins[0]['value']!=value or pins[0]['connected_pins']:raise ValueError('Pin default or unexpected data connection: '+key)
  then=[p for p in actual['output_pins'] if p['name']=='then']
  if len(then)!=1:raise ValueError('Missing execution output')
  links=then[0]['connected_pins']
  if index==len(expected)-1:
   if links:raise ValueError('Unexpected trailing execution connection')
  else:
   if len(links)!=1 or links[0]['direction']!='EGPD_Input':raise ValueError('Broken execution chain')
   target=by_ref.get(links[0]['node']['refPath'])
   if target is None:raise ValueError('Execution target absent')
   inputs=[p for p in target['input_pins'] if p['name']=='execute']
   if len(inputs)!=1 or inputs[0]['pin_id']!=links[0] or inputs[0]['connected_pins']!=[then[0]['pin_id']]:raise ValueError('Execution pins mismatch')
   actual=target
 if len(seen)!=len(infos):raise ValueError('Unreachable nodes')
 return mapping

def read_graph(session,blueprint):
 graph=session.invoke('BlueprintTools','get_graph',blueprint=blueprint,graph_name='EventGraph')
 refs=session.invoke('BlueprintTools','find_nodes',graph=graph,title='')
 infos=session.invoke('BlueprintTools','get_node_infos',nodes=refs)
 dsl=session.invoke('BlueprintTools','read_graph_dsl',graph=graph)
 return graph,infos,dsl

def compile_and_verify(session,blueprint,spec):
 result={'compilation_attempted':True,'compilation_result':'UNKNOWN','compiler_warnings':None,'compiler_errors':None,'diagnostics_limitation':'Native compile tool has no status payload. ObjectTools resolves Blueprint to CDO, so Status is unavailable.'}
 try:
  response=session.invoke('BlueprintTools','compile_blueprint',blueprint=blueprint,warnings_as_errors=True)
  result['native_response']=response
  _,infos,dsl=read_graph(session,blueprint)
  result['node_mapping']=compare_graph(spec,infos);result['readback_verification']=True;result['readback_dsl']=dsl
  result['generated_class']=session.invoke('ObjectTools','get_class',instance=blueprint)
  # No exception alone is not an explicit compiler result. Fail closed.
  result['compilation_result']='STATUS_UNAVAILABLE'
 except Exception as exc:
  result['compilation_result']='FAILED';result['compiler_errors']=[str(exc)]
 return result
