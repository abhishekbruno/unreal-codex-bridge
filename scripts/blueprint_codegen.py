"""Deterministic Epic DSL generation from validated, bounded specifications."""
from blueprint_spec import validate_spec, ordered_nodes
from blueprint_parser import tokenize_dsl, parse_sexpr

def quote(value):
 # Epic handles quote/backslash escapes, not JSON \\n or \\u escape decoding.
 return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'

def generate_dsl(spec):
 spec=validate_spec(spec)
 calls=['  (Development|PrintString :InString '+quote(n['defaults']['InString'])+')' for n in ordered_nodes(spec)[1:]]
 code='(event EventBeginPlay ()\n'+'\n'.join(calls)+'\n)\n'
 if len(code.encode('utf8'))>262144:raise ValueError('DSL size exceeds bound')
 trees=parse_sexpr(tokenize_dsl(code,strict=True),strict=True)
 if len(trees)!=1 or trees[0][:3]!=['event','EventBeginPlay',[]]:raise ValueError('Generated AST mismatch')
 expected=[n['defaults']['InString'] for n in ordered_nodes(spec)[1:]]
 if [c[2] for c in trees[0][3:]]!=expected:raise ValueError('String round-trip mismatch')
 return code
