"""Bounded declarative Actor Blueprint subset. No user supplied DSL/code."""
import copy
import re

ALLOWED_ROOTS = ('/Game/CodexBridgeTests/Blueprints/', '/Game/ARC02_Tests/')
ROOT = '/Game/CodexBridgeTests/Blueprints/'

EVENT_TYPES = {
    'AddEvent|EventBeginPlay',
    'AddEvent|EventTick',
    'AddEvent|Collision|EventActorBeginOverlap',
}

PINS = {
    'AddEvent|EventBeginPlay': {'then': ('output', 'Exec')},
    'AddEvent|EventTick': {'then': ('output', 'Exec'), 'DeltaSeconds': ('output', 'Float')},
    'AddEvent|Collision|EventActorBeginOverlap': {'then': ('output', 'Exec'), 'OtherActor': ('output', 'Object')},
    'Actor|K2_AddActorLocalRotation': {'execute': ('input', 'Exec'), 'then': ('output', 'Exec'), 'DeltaRotation': ('input', 'Rotator')},
    'Actor|K2_DestroyActor': {'execute': ('input', 'Exec'), 'then': ('output', 'Exec'), 'Target': ('input', 'Object')},
    'Actor|SetActorHiddenInGame': {'execute': ('input', 'Exec'), 'then': ('output', 'Exec'), 'bNewHidden': ('input', 'Boolean')},
    'Actor|SetActorEnableCollision': {'execute': ('input', 'Exec'), 'then': ('output', 'Exec'), 'bNewActorEnableCollision': ('input', 'Boolean')},
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
        allowed_defaults = ()
        if n['type'] == 'Development|PrintString':
            allowed_defaults = ('InString',)
        elif n['type'] == 'Actor|SetActorHiddenInGame':
            allowed_defaults = ('bNewHidden',)
        elif n['type'] == 'Actor|SetActorEnableCollision':
            allowed_defaults = ('bNewActorEnableCollision',)
        keys(n['defaults'], allowed_defaults,
             ('InString',) if n['type'] == 'Development|PrintString' else (), 'defaults')
        if n['defaults'] and 'InString' in n['defaults']:
            v = n['defaults']['InString']
            require(isinstance(v, str) and len(v) <= 4096 and not any(ord(ch) < 32 and ch not in '\n\r\t' for ch in v),
                    'InString', 'expected bounded text without control codes')
        if 'position' in n:
            require(isinstance(n['position'], list) and len(n['position']) == 2 and all(type(v) is int and abs(v) <= 100000 for v in n['position']),
                    'position', 'expected two bounded integers')
        nodes[n['id']] = n

    event_roots = [n['id'] for n in nodes.values() if n['type'] in EVENT_TYPES]
    require(len(event_roots) >= 1, 'nodes', 'at least one event node required')
    require(isinstance(g['connections'], list) and len(g['connections']) == len(nodes) - len(event_roots),
            'connections', 'all nodes must form one execution chain' if len(event_roots) == 1 else 'all nodes must form execution chains from event roots')

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
        require(nodes[b]['type'] not in EVENT_TYPES, 'connection', 'cannot connect into event root')
        outgoing[a] = b
        incoming.add(b)

    begin_roots = [r for r in event_roots if nodes[r]['type'] == 'AddEvent|EventBeginPlay']
    other_roots = [r for r in event_roots if nodes[r]['type'] != 'AddEvent|EventBeginPlay']
    ordered_roots = begin_roots + other_roots
    seen = set()
    for root in ordered_roots:
        curr = root
        while curr:
            require(curr not in seen, 'connections', 'cycle')
            seen.add(curr)
            curr = outgoing.get(curr)
    require(seen == set(nodes), 'connections', 'disconnected nodes')
    return copy.deepcopy(spec)


def ordered_nodes(spec):
    g = spec['graphs'][0]
    nodes = {n['id']: n for n in g['nodes']}
    nexts = {c['from']['node']: c['to']['node'] for c in g['connections']}
    event_roots = [n['id'] for n in nodes.values() if n['type'] in EVENT_TYPES]
    begin_roots = [r for r in event_roots if nodes[r]['type'] == 'AddEvent|EventBeginPlay']
    other_roots = [r for r in event_roots if nodes[r]['type'] != 'AddEvent|EventBeginPlay']
    result = []
    for root in begin_roots + other_roots:
        current = root
        while current:
            result.append(nodes[current])
            current = nexts.get(current)
    return result


def ordered_chains(spec):
    g = spec['graphs'][0]
    nodes = {n['id']: n for n in g['nodes']}
    nexts = {c['from']['node']: c['to']['node'] for c in g['connections']}
    event_roots = [n['id'] for n in nodes.values() if n['type'] in EVENT_TYPES]
    begin_roots = [r for r in event_roots if nodes[r]['type'] == 'AddEvent|EventBeginPlay']
    other_roots = [r for r in event_roots if nodes[r]['type'] != 'AddEvent|EventBeginPlay']
    chains = []
    for root in begin_roots + other_roots:
        chain = []
        current = root
        while current:
            chain.append(nodes[current])
            current = nexts.get(current)
        chains.append(chain)
    return chains


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


def collectible_cube_spec(name='BP_ARC02_CollectibleCube', folder='/Game/ARC02_Tests/'):
    return {
        'name': name,
        'parent_class': '/Script/Engine.Actor',
        'asset_path': folder + name,
        'variables': [
            {'name': 'ScoreValue', 'type': 'int', 'default': 1},
            {'name': 'IsCollected', 'type': 'bool', 'default': False},
            {'name': 'CubeIndex', 'type': 'int', 'default': 0},
        ],
        'components': [
            {
                'name': 'CubeMesh',
                'type': '/Script/Engine.StaticMeshComponent',
                'properties': {
                    'StaticMesh': '/Engine/BasicShapes/Cube.Cube',
                    'CollisionProfileName': 'OverlapAllDynamic',
                }
            },
            {
                'name': 'RotatingMovement',
                'type': '/Script/Engine.RotatingMovementComponent',
                'properties': {
                    'RotationRate': {'Pitch': 0.0, 'Yaw': 90.0, 'Roll': 0.0}
                }
            }
        ],
        'graphs': [{
            'name': 'EventGraph',
            'nodes': [
                {'id': 'begin', 'type': 'AddEvent|EventBeginPlay', 'defaults': {}},
                {'id': 'print_ready', 'type': 'Development|PrintString',
                 'defaults': {'InString': 'ARC02 Collectible Cube Ready [pickup]'}},
                {'id': 'overlap', 'type': 'AddEvent|Collision|EventActorBeginOverlap', 'defaults': {}},
                {'id': 'print_collect', 'type': 'Development|PrintString',
                 'defaults': {'InString': 'ARC02 Cube Collected! +1 point [pickup] [score]'}},
                {'id': 'destroy', 'type': 'Actor|K2_DestroyActor', 'defaults': {}}
            ],
            'connections': [
                {'from': {'node': 'begin', 'pin': 'then'}, 'to': {'node': 'print_ready', 'pin': 'execute'}},
                {'from': {'node': 'overlap', 'pin': 'then'}, 'to': {'node': 'print_collect', 'pin': 'execute'}},
                {'from': {'node': 'print_collect', 'pin': 'then'}, 'to': {'node': 'destroy', 'pin': 'execute'}}
            ]
        }]
    }


def game_manager_spec(name='BP_ARC02_GameManager', folder='/Game/ARC02_Tests/'):
    return {
        'name': name,
        'parent_class': '/Script/Engine.Actor',
        'asset_path': folder + name,
        'variables': [
            {'name': 'CurrentScore', 'type': 'int', 'default': 0},
            {'name': 'TargetScore', 'type': 'int', 'default': 3},
        ],
        'components': [],
        'graphs': [{
            'name': 'EventGraph',
            'nodes': [
                {'id': 'begin', 'type': 'AddEvent|EventBeginPlay', 'defaults': {}},
                {'id': 'print_init', 'type': 'Development|PrintString',
                 'defaults': {'InString': 'ARC02 Game Manager Active. 3 Collectibles Spawned [score]'}}
            ],
            'connections': [
                {'from': {'node': 'begin', 'pin': 'then'}, 'to': {'node': 'print_init', 'pin': 'execute'}}
            ]
        }]
    }
