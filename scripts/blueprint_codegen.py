"""Deterministic Epic DSL generation from validated, bounded specifications."""
from blueprint_spec import validate_spec, ordered_nodes, ordered_chains
from blueprint_parser import tokenize_dsl, parse_sexpr

def quote(value):
    # Epic handles quote/backslash escapes, not JSON \\n or \\u escape decoding.
    return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'

def generate_dsl(spec):
    spec = validate_spec(spec)
    chains = ordered_chains(spec)

    # Fast path: single BeginPlay chain with only PrintStrings (exact round-trip check)
    if len(chains) == 1 and chains[0][0]['type'] == 'AddEvent|EventBeginPlay' and all(n['type'] == 'Development|PrintString' for n in chains[0][1:]):
        calls = ['  (Development|PrintString :InString '+quote(n['defaults']['InString'])+')' for n in chains[0][1:]]
        code = '(event EventBeginPlay ()\n'+'\n'.join(calls)+'\n)\n'
        if len(code.encode('utf8')) > 262144: raise ValueError('DSL size exceeds bound')
        trees = parse_sexpr(tokenize_dsl(code, strict=True), strict=True)
        if len(trees) != 1 or trees[0][:3] != ['event', 'EventBeginPlay', []]: raise ValueError('Generated AST mismatch')
        expected = [n['defaults']['InString'] for n in chains[0][1:]]
        if [c[2] for c in trees[0][3:]] != expected: raise ValueError('String round-trip mismatch')
        return code

    event_blocks = []
    for chain in chains:
        root = chain[0]
        event_name = root['type'].split('|')[-1]
        calls = []
        for n in chain[1:]:
            ntype = n['type']
            if ntype == 'Development|PrintString':
                calls.append('  (Development|PrintString :InString ' + quote(n['defaults']['InString']) + ')')
            elif ntype == 'Actor|K2_DestroyActor':
                calls.append('  (Actor|K2_DestroyActor)')
            elif ntype == 'Actor|K2_AddActorLocalRotation':
                calls.append('  (Actor|K2_AddActorLocalRotation)')
            elif ntype == 'Actor|SetActorHiddenInGame':
                val = 'true' if n['defaults'].get('bNewHidden', True) else 'false'
                calls.append(f'  (Actor|SetActorHiddenInGame :bNewHidden {val})')
            elif ntype == 'Actor|SetActorEnableCollision':
                val = 'true' if n['defaults'].get('bNewActorEnableCollision', True) else 'false'
                calls.append(f'  (Actor|SetActorEnableCollision :bNewActorEnableCollision {val})')
            else:
                calls.append(f'  ({ntype})')
        body = '\n'.join(calls)
        if body:
            event_blocks.append(f'(event {event_name} ()\n{body}\n)')
        else:
            event_blocks.append(f'(event {event_name} ()\n)')
    code = '\n'.join(event_blocks) + '\n'
    if len(code.encode('utf8')) > 262144: raise ValueError('DSL size exceeds bound')
    trees = parse_sexpr(tokenize_dsl(code, strict=True), strict=True)
    if len(trees) != len(chains): raise ValueError('Generated AST mismatch')
    return code
