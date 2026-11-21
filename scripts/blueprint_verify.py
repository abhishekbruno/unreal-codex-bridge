"""Semantic graph, component, and variable verification for Blueprints."""
import json
from blueprint_spec import ordered_nodes, validate_spec


def compare_graph(spec, infos):
    expected = ordered_nodes(validate_spec(spec))
    if len(infos) != len(expected):
        raise ValueError(f'Node count mismatch: {len(infos)} != {len(expected)}')
    starts = [n for n in infos if n['type_id'] == 'AddEvent|EventBeginPlay']
    if len(starts) != 1:
        raise ValueError('BeginPlay count mismatch')
    by_ref = {n['node']['refPath']: n for n in infos}
    actual = starts[0]
    mapping = {}
    seen = set()
    for index, wanted in enumerate(expected):
        ref = actual['node']['refPath']
        if ref in seen or actual['type_id'] != wanted['type']:
            raise ValueError('Unexpected node type or cycle')
        seen.add(ref)
        mapping[wanted['id']] = actual['node']
        if 'position' in wanted and actual['position'] != {'x': wanted['position'][0], 'y': wanted['position'][1]}:
            raise ValueError('Node position mismatch')
        for key, value in wanted['defaults'].items():
            pins = [p for p in actual['input_pins'] if p['name'] == key]
            if len(pins) != 1 or pins[0]['value'] != value or pins[0]['connected_pins']:
                raise ValueError('Pin default or unexpected data connection: ' + key)
        then = [p for p in actual['output_pins'] if p['name'] == 'then']
        if len(then) != 1:
            raise ValueError('Missing execution output')
        links = then[0]['connected_pins']
        if index == len(expected) - 1:
            if links:
                raise ValueError('Unexpected trailing execution connection')
        else:
            if len(links) != 1 or links[0]['direction'] != 'EGPD_Input':
                raise ValueError('Broken execution chain')
            target = by_ref.get(links[0]['node']['refPath'])
            if target is None:
                raise ValueError('Execution target absent')
            inputs = [p for p in target['input_pins'] if p['name'] == 'execute']
            if len(inputs) != 1 or inputs[0]['pin_id'] != links[0] or inputs[0]['connected_pins'] != [then[0]['pin_id']]:
                raise ValueError('Execution pins mismatch')
            actual = target
    if len(seen) != len(infos):
        raise ValueError('Unreachable nodes')
    return mapping


def read_graph(session, blueprint):
    graph = session.invoke('BlueprintTools', 'get_graph', blueprint=blueprint, graph_name='EventGraph')
    refs = session.invoke('BlueprintTools', 'find_nodes', graph=graph, title='')
    infos = session.invoke('BlueprintTools', 'get_node_infos', nodes=refs)
    dsl = session.invoke('BlueprintTools', 'read_graph_dsl', graph=graph)
    return graph, infos, dsl


def verify_components(session, blueprint, expected_components):
    if not expected_components:
        return {'verified': True, 'components': []}
    cdo = session.invoke('BlueprintTools', 'get_default_object', blueprint=blueprint)
    comps = session.invoke('ActorTools', 'get_components', actor=cdo)
    comp_refs = {c.get('refPath', ''): c for c in comps}
    verified_comps = []
    for wanted in expected_components:
        name = wanted['name']
        matching = [r for r in comp_refs if f'{name}_GEN_VARIABLE' in r or r.endswith(f':{name}')]
        if not matching:
            raise ValueError(f'Component not found on CDO: {name}')
        comp_ref = comp_refs[matching[0]]
        comp_entry = {'name': name, 'ref': comp_ref, 'properties': {}}
        if wanted.get('properties'):
            prop_names = list(wanted['properties'].keys())
            raw_props = session.invoke('ObjectTools', 'get_properties', instance=comp_ref, properties=prop_names)
            props_dict = json.loads(raw_props) if isinstance(raw_props, str) else (raw_props or {})
            for pk, pv in wanted['properties'].items():
                actual_val = props_dict.get(pk)
                if isinstance(pv, str) and isinstance(actual_val, dict) and 'refPath' in actual_val:
                    actual_path = actual_val['refPath']
                    if actual_path != pv:
                        raise ValueError(f'Component {name} property {pk} mismatch: {actual_path} != {pv}')
                elif actual_val != pv:
                    raise ValueError(f'Component {name} property {pk} mismatch: {actual_val} != {pv}')
                comp_entry['properties'][pk] = actual_val
        verified_comps.append(comp_entry)
    return {'verified': True, 'components': verified_comps}


def verify_variables(session, blueprint, expected_variables):
    if not expected_variables:
        return {'verified': True, 'variables': []}
    var_names = session.invoke('BlueprintTools', 'list_variables', blueprint=blueprint)
    cdo = None
    verified_vars = []
    for wanted in expected_variables:
        name = wanted['name']
        if name not in var_names:
            raise ValueError(f'Variable not found on blueprint: {name}')
        var_entry = {'name': name, 'type': wanted['type']}
        if 'default' in wanted:
            if cdo is None:
                cdo = session.invoke('BlueprintTools', 'get_default_object', blueprint=blueprint)
            raw_props = session.invoke('ObjectTools', 'get_properties', instance=cdo, properties=[name])
            props_dict = json.loads(raw_props) if isinstance(raw_props, str) else (raw_props or {})
            actual_val = props_dict.get(name)
            if actual_val != wanted['default']:
                raise ValueError(f'Variable {name} default mismatch: {actual_val} != {wanted["default"]}')
            var_entry['default'] = actual_val
        verified_vars.append(var_entry)
    return {'verified': True, 'variables': verified_vars}


def compile_and_verify(session, blueprint, spec):
    result = {
        'compilation_attempted': True,
        'compilation_result': 'UNKNOWN',
        'compiler_warnings': None,
        'compiler_errors': None,
        'readback_verification': False,
    }
    try:
        response = session.invoke('BlueprintTools', 'compile_blueprint', blueprint=blueprint, warnings_as_errors=True)
        result['native_response'] = response
        _, infos, dsl = read_graph(session, blueprint)
        result['node_mapping'] = compare_graph(spec, infos)
        result['readback_verification'] = True
        result['readback_dsl'] = dsl
        result['generated_class'] = session.invoke('ObjectTools', 'get_class', instance=blueprint)
        if spec.get('variables'):
            result['variables'] = verify_variables(session, blueprint, spec['variables'])
        if spec.get('components'):
            result['components'] = verify_components(session, blueprint, spec['components'])
        result['compilation_result'] = 'COMPILED'
    except Exception as exc:
        result['compilation_result'] = 'FAILED'
        result['compiler_errors'] = [str(exc)]
    return result
