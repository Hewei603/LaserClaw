"""Independently verify the approved case using bundled evidence only."""
from copy import deepcopy
import json
import math
from pathlib import Path

import numpy as np


def element_matrix(element):
    if element['kind'] == 'space':
        return np.array([[1., element.get('length_mm', 0)/element.get('n', 1)], [0, 1.]])
    if element['kind'] == 'lens':
        return np.array([[1., 0], [-1/element['focal_mm'], 1.]])
    if element['kind'] == 'mirror':
        assert element.get('aoi_deg', 0) == 0
        curvature = element.get('radius_mm')
        return np.array([[1., 0], [0 if curvature is None else -2/curvature, 1.]])
    raise AssertionError('This independent reference covers this case: space, lens, normal mirror.')


def round_trip(system):
    assert system['mode'] == 'standing_wave'
    elements = system['elements']
    result = np.eye(2)
    for element in [*elements[1:], *reversed(elements[1:-1]), elements[0]]:
        result = element_matrix(element) @ result
    return result


def main():
    root = Path(__file__).resolve().parent
    run = json.loads((root/'run-final.json').read_text(encoding='utf-8'))
    saved = json.loads((root/'project36.json').read_text(encoding='utf-8'))
    calls = {call['id']: call for call in run['tools']}
    assert run['status'] == 'partial'
    assert all(call['status'] == 'completed' for call in calls.values())
    assert len([call for call in calls.values() if call['name'] != 'finish']) == 10
    matrix_error, radius_error = 0., 0.
    for analysis in [saved['analysis'], calls[76]['output'], calls[79]['output']]:
        system = analysis['system']
        matrix = round_trip(system)
        a, b, c, d = matrix.ravel()
        m = (a+d)/2
        roots = np.roots([c, d-a, -b])
        q = next(value for value in roots if value.imag > 0)
        nodes = [q]
        for element in system['elements'][1:]:
            a, b, c, d = element_matrix(element).ravel()
            q = (a*q+b)/(c*q+d)
            nodes.append(q)
        radii = [math.sqrt(system['wavelength_nm']*1e-6/math.pi*abs(value)**2/value.imag) for value in nodes]
        for plane in analysis['planes'].values():
            matrix_error = max(matrix_error, float(np.max(np.abs(matrix-np.array(plane['matrix'])))), abs(m-plane['m']))
            assert plane['stable'] == (abs(m) < 1)
            assert len(radii) == len(plane['elements'])
            radius_error = max(radius_error, max(abs(w-p['radius_mm']) for w, p in zip(radii, plane['elements'])))
    assert matrix_error < 1e-10 and radius_error < 1e-10
    checked = 0
    for call_id in (72, 73):
        call = calls[call_id]
        config, output = call['input'], call['output']
        for row, y in enumerate(output['y']):
            for column, x in enumerate(output['x']):
                system = deepcopy(config['system'])
                for axis, value in ((config['x'], x), (config['y'], y)):
                    system['elements'][axis['element_index']][axis['parameter']] = value
                m = float(np.trace(round_trip(system))/2)
                for plane in ('tangential', 'sagittal'):
                    assert abs(m-output['maps'][plane][row][column]) < 1e-10
                assert (abs(m) < 1) == bool(output['maps']['stable_both'][row][column])
                checked += 1
    assert checked == 3538
    print(json.dumps({'passed': True, 'map_points': checked, 'maximum_matrix_or_m_error': matrix_error,
                      'maximum_radius_error_mm': radius_error, 'power_optimum_established': False}, indent=2))


if __name__ == '__main__':
    main()
