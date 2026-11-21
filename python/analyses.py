import copy
import math
import statistics
import time
from collections.abc import Callable

from engine.inputs import GREEKS, normalize_request, number


ENGINES = ('python', 'vba')


def calculator(engine: str) -> Callable:
    """On renvoie la fonction de calcul du moteur Python ou VBA demandé"""
    if engine == 'python':
        from engine.service import calculate
    elif engine == 'vba':
        from excel_bridge import calculate
    else:
        raise ValueError('Moteur inconnu')
    return calculate


def selected_engines(request: dict) -> tuple:
    """On garde le même ordre pour les tableaux et les courbes de comparaison"""
    engine = request.get('engine', 'python')
    if engine not in ('python', 'vba', 'both'):
        raise ValueError('Choisir Python, VBA ou les deux moteurs')
    return ENGINES if engine == 'both' else (engine,)


def run_engines(request: dict, progress: Callable) -> dict:
    """On calcule les résultats avec chacun des moteurs sélectionnés"""
    results = {}
    for engine in selected_engines(request):
        progress('Calcul ' + engine.upper())
        results[engine] = calculator(engine)(request)
    return results


def metric_value(report: dict, metric: str) -> float:
    """On compare les grecs dans les unités affichées par le moteur"""
    if metric == 'price':
        return report['price']
    row = report['greeks'].get(metric, {})
    value = row.get('value')
    if value is None or not math.isfinite(value):
        raise ValueError(row.get('warning') or f'Le grec {metric} est indisponible')
    return value


def price_only(request: dict, metric: str = 'price') -> dict:
    """On prépare une copie qui calcule uniquement le prix ou le grec étudié"""
    result = copy.deepcopy(request)
    result['greeks'] = [] if metric == 'price' else [metric]
    return result


def reference_value(request: dict, metric: str, steps: list, progress: Callable) -> dict:
    """On choisit Black-Scholes ou un arbre Python plus fin comme référence"""
    from engine.analytic import black_scholes_reference
    work = price_only(request, metric)
    try:
        value = metric_value(black_scholes_reference(work), metric)
        return {'value': value, 'label': 'Black–Scholes analytique', 'empirical': False}
    except ValueError:
        maximum = max(steps)
        if maximum >= 10000:
            raise ValueError('Choisir moins de 10 000 pas pour comparer avec un arbre plus précis')
    # On prend sinon un arbre Python plus fin que tous les points comparés
    count = min(10000, maximum * 2)
    work['grid']['steps'] = count
    progress(f'Référence PYTHON — {count} pas')
    report = calculator('python')(work)
    return {'value': metric_value(report, metric), 'label': f'Arbre PYTHON à {count} pas',
            'empirical': True, 'steps': count}


def convergence(request: dict, settings: dict, progress: Callable) -> dict:
    """On conserve le pruning choisi dans la position et on choisit les pas automatiquement"""
    tolerance = number(settings.get('tolerance', 0.001), 'La tolérance')
    if tolerance <= 0:
        raise ValueError('La tolérance doit être strictement positive')
    steps = automatic_steps(request)
    metric = settings.get('metric', 'price')
    reference = reference_value(request, metric, steps, progress)
    rows = _convergence_rows(request, metric, steps, reference, progress)
    return {'rows': rows, 'reference': reference, 'tolerance': tolerance,
            'thresholds': tolerance_results(rows, tolerance),
            'note': 'La précision concerne les nombres de pas testés ; la convergence peut osciller'}


def _convergence_rows(request: dict, metric: str, steps: list,
                     reference: dict, progress: Callable) -> list:
    """On mesure le résultat et son erreur pour chaque nombre de pas"""
    rows = []
    for engine in selected_engines(request):
        work = price_only(request, metric)
        for count in steps:
            progress(f'{engine.upper()} — {count} pas')
            work['grid']['steps'] = count
            report = _grid_calculation(engine, work)
            value = metric_value(report, metric)
            error = abs(value - reference['value'])
            rows.append({'engine': engine, 'steps': count, 'value': value, 'error': error,
                         'relative_error': error / abs(reference['value']) if reference['value'] else None,
                         'seconds': report['timings']['total']})
    return rows


def _grid_calculation(engine: str, request: dict) -> dict:
    """On valorise les paramètres en précisant le nombre de pas si une erreur survient"""
    try:
        return calculator(engine)(request)
    except (ValueError, RuntimeError) as error:
        grid = request['grid']
        raise ValueError(f"{engine.upper()}, {grid['steps']} pas, pruning {grid['pruning']:g} : {error}") from error


def tolerance_results(rows: list, tolerance: float) -> list:
    """On repère les nombres de pas à partir desquels tous les points testés respectent la tolérance"""
    result = []
    for engine in sorted(set(row['engine'] for row in rows)):
        # On classe les points par nombre de pas
        group = sorted((row for row in rows if row['engine'] == engine), key=lambda row: row['steps'])
        sustained = [row['steps'] for index, row in enumerate(group)
                     if all(item['error'] < tolerance for item in group[index:])]
        result.append({'engine': engine, 'remaining_tested': min(sustained, default=None)})
    return result


def benchmark(request: dict, progress: Callable) -> dict:
    """On compare les temps des moteurs avec deux répétitions par nombre de pas"""
    rows = []
    for engine in selected_engines(request):
        work = price_only(request)
        for count in automatic_steps(request):
            work['grid']['steps'] = count
            progress(f'{engine.upper()} — {count} pas — 2 répétitions')
            rows.append(_benchmark_point(engine, work))
    return {'rows': rows, 'repeats': 2,
            'note': 'Chaque instrument est construit et valorisé séparément dans les deux moteurs, sans cache ; '
                    'médianes des sommes par position, calcul seul = construction + remontée ; '
                    'démarrage Excel et aller-retour mesurés séparément'}


def _benchmark_point(engine: str, request: dict) -> dict:
    """On sépare le temps du moteur du temps aller-retour de son appel"""
    samples = [_benchmark_sample(engine, request) for _ in range(2)]
    keys = set.intersection(*(set(sample) for sample in samples)) - {'value'}
    row = {key: statistics.median(sample[key] for sample in samples) for key in keys}
    row.update(engine=engine, steps=request['grid']['steps'], value=samples[-1]['value'])
    return row


def _benchmark_sample(engine: str, request: dict) -> dict:
    """On mesure un calcul complet en construisant chaque instrument séparément"""
    start = time.perf_counter()
    reports = []
    for leg in request['legs']:
        work = copy.deepcopy(request)
        work['legs'] = [copy.deepcopy(leg)]
        reports.append(calculator(engine)(work))
    keys = set.intersection(*(set(report['timings']) for report in reports))
    sample = {key: sum(report['timings'][key] for report in reports) for key in keys}
    sample.update(core=sample['build'] + sample['price'], roundtrip=time.perf_counter() - start,
                  value=sum(report['price'] for report in reports))
    return sample


def tree_view(request: dict, progress: Callable) -> dict:
    """On limite le détail à un petit arbre lisible dans le navigateur"""
    results = {}
    if request['grid']['steps'] > 12:
        raise ValueError('La visualisation détaillée est limitée à 12 pas')
    request = copy.deepcopy(request)
    request['legs'] = request['legs'][:1]
    for engine in selected_engines(request):
        progress('Construction des nœuds ' + engine.upper())
        if engine == 'python':
            from engine.pricing import export_tree
        else:
            from excel_bridge import export_tree
        results[engine] = export_tree(request)
    return results


def automatic_steps(request: dict) -> list:
    """On choisit les points des graphiques à partir du nombre de pas demandé"""
    maximum = number(request['grid']['steps'], 'Le nombre de pas')
    if not 1 <= maximum <= 10000 or maximum != int(maximum):
        raise ValueError('Choisir un nombre entier de pas entre 1 et 10 000')
    return sorted(set(max(1, round(maximum * ratio)) for ratio in (0.0625, 0.125, 0.25, 0.5, 0.75, 1)))


def greek_curve(request: dict, settings: dict, progress: Callable) -> dict:
    """On calcule la courbe seulement pour le grec ouvert par l'utilisateur"""
    from engine.derivatives import UNITS
    metric = settings.get('metric')
    if metric not in GREEKS:
        raise ValueError('Choisir un grec disponible')
    request = normalize_request(request)
    center = request['market']['spot']
    spots = [center * (0.8 + index * 0.05) for index in range(9)]
    rows = []
    for engine in selected_engines(request):
        work = price_only(request, metric)
        for spot in spots:
            progress(f'{engine.upper()} — spot {spot:g}')
            work['market']['spot'] = spot
            report = calculator(engine)(work)
            rows.append({'engine': engine, 'spot': spot, 'value': metric_value(report, metric)})
    return {'rows': rows, 'metric': metric, 'unit': UNITS[metric]}


def execute(payload: dict, progress: Callable) -> dict:
    """On dirige la demande vers la valorisation ou l’analyse choisie"""
    request = normalize_request(payload['request'])
    settings = payload.get('settings', {})
    action = payload.get('action', 'price')
    if action in ('price', 'greeks'):
        return {'action': action, 'results': run_engines(request, progress)}
    if action == 'tree':
        return {'action': action, 'results': tree_view(request, progress)}
    if action == 'benchmark':
        return {'action': action, **benchmark(request, progress)}
    functions = {'convergence': convergence, 'curve': greek_curve}
    if action not in functions:
        raise ValueError('Analyse inconnue')
    return {'action': action, **functions[action](request, settings, progress)}
