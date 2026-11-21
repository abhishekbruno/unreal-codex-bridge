"""Bounded declarative Actor Blueprint subset. No user supplied DSL/code."""
import copy
import re

ALLOWED_ROOTS = ('/Game/CodexBridgeTests/Blueprints/', '/Game/ARC02_Tests/')
ROOT = '/Game/CodexBridgeTests/Blueprints/'

PINS = {
    'AddEvent|EventBeginPlay': {'then': ('output', 'Exec')},
    'Development|PrintString': {'execute': ('input', 'Exec'), 'then': ('output', 'Exec'), 'InString': ('input', 'String')},
}

VALID_VAR_TYPES = {
    'bool', 'int', 'float', 'byte', 'name', 'string', 'text',
    'Vector', 'Rotator', 'Transform', 'Vector2D', 'LinearColor'
}


class SpecError(ValueError):
    def __init__(self, path, message):
        self.errors = [{'path': path, 'message': message}]
        super().__init__(f'{path}: {message}')


def require(ok, path, message):
    if not ok:
        raise SpecError(path, message)


def keys(obj, allowed, required, path):
    require(isinstance(obj, dict), path, 'must be an object')
    require(set(obj) <= set(allowed), path, 'unknown fields')
    require(set(required) <= set(obj), path, 'missing required fields')


def validate_spec(spec):
    keys(spec, ('name', 'parent_class', 'asset_path', 'graphs', 'variables', 'components'),
         ('name', 'parent_class', 'asset_path', 'graphs', 'variables'), 'spec')

    require(isinstance(spec['name'], str) and re.fullmatch(r'BP_[A-Za-z0-9_]{1,80}', spec['name']),
            'name', 'invalid isolated test name')

    valid_path = any(
        spec['asset_path'].startswith(r) and spec['asset_path'] == r + spec['name']
        for r in ALLOWED_ROOTS
    ) and '..' not in spec['asset_path']
    require(valid_path, 'asset_path', 'must be an allowed isolated test path matching name')

    require(spec['parent_class'] == '/Script/Engine.Actor', 'parent_class', 'only Actor supported')

    # Validate variables
    require(isinstance(spec['variables'], list), 'variables', 'must be a list')
    var_names = set()
    for v in spec['variables']:
        keys(v, ('name', 'type', 'default'), ('name', 'type'), 'variable')
        require(isinstance(v['name'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', v['name']),
                'variable.name', 'invalid variable name')
        require(v['name'] not in var_names, 'variable.name', 'duplicate variable name')
        var_names.add(v['name'])
        require(isinstance(v['type'], str) and v['type'] in VALID_VAR_TYPES,
                'variable.type', f"unsupported variable type: {v.get('type')}")
        if 'default' in v:
            d = v['default']
            t = v['type']
            if t == 'bool':
                require(isinstance(d, bool), 'variable.default', 'expected bool')
            elif t in ('int', 'byte'):
                require(type(d) is int and not isinstance(d, bool), 'variable.default', 'expected int')
            elif t == 'float':
                require((isinstance(d, float) or type(d) is int) and not isinstance(d, bool),
                        'variable.default', 'expected number')
            elif t in ('string', 'name', 'text'):
                require(isinstance(d, str), 'variable.default', 'expected str')

    # Validate components if provided
    if 'components' in spec:
        require(isinstance(spec['components'], list), 'components', 'must be a list')
        comp_names = set()
        for c in spec['components']:
            keys(c, ('name', 'type', 'properties'), ('name', 'type'), 'component')
            require(isinstance(c['name'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', c['name']),
                    'component.name', 'invalid component name')
            require(c['name'] not in comp_names, 'component.name', 'duplicate component name')
            comp_names.add(c['name'])
            require(isinstance(c['type'], str) and re.fullmatch(r'/Script/Engine\.[A-Za-z0-9_]+Component', c['type']),
                    'component.type', 'unsupported component type')
            if 'properties' in c:
                require(isinstance(c['properties'], dict), 'component.properties', 'must be an object')
                for pk in c['properties']:
                    require(isinstance(pk, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', pk),
                            'component.property.key', 'invalid property name')

    # Validate graph
    require(isinstance(spec['graphs'], list) and len(spec['graphs']) == 1, 'graphs', 'exactly one graph required')
    g = spec['graphs'][0]
    keys(g, ('name', 'nodes', 'connections'), ('name', 'nodes', 'connections'), 'graph')
    require(g['name'] == 'EventGraph', 'graph.name', 'only EventGraph supported')
    require(isinstance(g['nodes'], list) and 2 <= len(g['nodes']) <= 32, 'nodes', 'expected 2..32 nodes')

    nodes = {}
    for n in g['nodes']:
        keys(n, ('id', 'type', 'defaults', 'position'), ('id', 'type', 'defaults'), 'node')
        require(isinstance(n['id'], str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', n['id']),
                'node.id', 'invalid stable id')
        require(n['id'] not in nodes, 'node.id', 'duplicate id')
        require(isinstance(n['type'], str) and n['type'] in PINS, 'node.type', 'unsupported node')
        keys(n['defaults'], ('InString',) if n['type'] == 'Development|PrintString' else (),
             ('InString',) if n['type'] == 'Development|PrintString' else (), 'defaults')
        if n['defaults']:
            v = n['defaults']['InString']
            require(isinstance(v, str) and len(v) <= 4096 and not any(ord(ch) < 32 and ch not in '\n\r\t' for ch in v),
                    'InString', 'expected bounded text without control codes')
        if 'position' in n:
            require(isinstance(n['position'], list) and len(n['position']) == 2 and all(type(v) is int and abs(v) <= 100000 for v in n['position']),
                    'position', 'expected two bounded integers')
        nodes[n['id']] = n

    require(sum(n['type'] == 'AddEvent|EventBeginPlay' for n in nodes.values()) == 1, 'nodes', 'exactly one BeginPlay required')
    require(isinstance(g['connections'], list) and len(g['connections']) == len(nodes) - 1,
            'connections', 'all nodes must form one execution chain')

    outgoing = {}
    incoming = set()
    for c in g['connections']:
        keys(c, ('from', 'to'), ('from', 'to'), 'connection')
        pins = []
        for side, direction in [('from', 'output'), ('to', 'input')]:
            e = c[side]
            keys(e, ('node', 'pin'), ('node', 'pin'), side)
            require(isinstance(e['node'], str) and e['node'] in nodes, side, 'undefined node')
            require(isinstance(e['pin'], str) and e['pin'] in PINS[nodes[e['node']]['type']], side, 'undefined pin')
            p = PINS[nodes[e['node']]['type']][e['pin']]
            require(p[0] == direction, side, 'invalid pin direction')
            pins.append(p)
        require(pins[0][1] == pins[1][1] == 'Exec', 'connection', 'only compatible execution links supported')
        a, b = c['from']['node'], c['to']['node']
        require(a not in outgoing and b not in incoming, 'connection', 'branch or multiple inputs unsupported')
        outgoing[a] = b
        incoming.add(b)

    start = next(n['id'] for n in nodes.values() if n['type'] == 'AddEvent|EventBeginPlay')
    seen = set()
    while start:
        require(start not in seen, 'connections', 'cycle')
        seen.add(start)
        start = outgoing.get(start)
    require(seen == set(nodes), 'connections', 'disconnected nodes')
    return copy.deepcopy(spec)


def ordered_nodes(spec):
    g = spec['graphs'][0]
    nodes = {n['id']: n for n in g['nodes']}
    nexts = {c['from']['node']: c['to']['node'] for c in g['connections']}
    current = next(n['id'] for n in nodes.values() if n['type'] == 'AddEvent|EventBeginPlay')
    result = []
    while current:
        result.append(nodes[current])
        current = nexts.get(current)
    return result


def example_spec(name='BP_CodexBridge_Test'):
    return {
        'name': name,
        'parent_class': '/Script/Engine.Actor',
        'asset_path': ROOT + name,
        'variables': [],
        'components': [],
        'graphs': [{
            'name': 'EventGraph',
            'nodes': [
                {'id': 'begin', 'type': 'AddEvent|EventBeginPlay', 'defaults': {}},
                {'id': 'print', 'type': 'Development|PrintString', 'defaults': {'InString': 'Unreal Codex Bridge: Blueprint execution successful'}}
            ],
            'connections': [{'from': {'node': 'begin', 'pin': 'then'}, 'to': {'node': 'print', 'pin': 'execute'}}]
        }]
    }


def test_cube_spec(name='BP_ARC02_TestCube', folder='/Game/ARC02_Tests/'):
    return {
        'name': name,
        'parent_class': '/Script/Engine.Actor',
        'asset_path': folder + name,
        'variables': [{'name': 'TestScore', 'type': 'int', 'default': 42}],
        'components': [{
            'name': 'CubeMesh',
            'type': '/Script/Engine.StaticMeshComponent',
            'properties': {'StaticMesh': '/Engine/BasicShapes/Cube.Cube'}
        }],
        'graphs': [{
            'name': 'EventGraph',
            'nodes': [
                {'id': 'begin', 'type': 'AddEvent|EventBeginPlay', 'defaults': {}},
                {'id': 'print', 'type': 'Development|PrintString', 'defaults': {'InString': 'Unreal Codex Bridge: ARC02 TestCube Active'}}
            ],
            'connections': [{'from': {'node': 'begin', 'pin': 'then'}, 'to': {'node': 'print', 'pin': 'execute'}}]
        }]
    }
