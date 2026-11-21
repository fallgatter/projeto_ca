from datetime import datetime
from functools import lru_cache
from math import cos, sin, tau
from statistics import fmean

from .io import read_json, write_json

from .simulate import BIN, OUTPUT, WARMUP


ORDERS = (2, 3, 4, 6)
RIDGE = .08
DAILY_PROFILE = [(0, .23), (3, .10), (5, .36), (7, 1.0), (11, .68), (14, .70),
                 (18, 1.0), (21, .42), (23, .27)]


@lru_cache(maxsize=4096)
def basis(second, order=2):
    angle = tau * second / 86400
    return (1., *(value for k in range(1, order+1) for value in (cos(k*angle), sin(k*angle))))


def predict(coefficients, second):
    return max(0., sum(coef * factor for coef, factor in
                       zip(coefficients, basis(second, (len(coefficients)-1)//2))))


def regress(rows, order=2):
    """Fit the Fourier coefficients by weighted ridge least squares."""
    size = 2*order+1
    matrix = [[0.] * (size+1) for _ in range(size)]
    for second, rate, weight in rows:
        terms = basis(second, order)
        for i, left in enumerate(terms):
            for j, right in enumerate(terms):
                matrix[i][j] += weight * left * right
            matrix[i][-1] += weight * left * rate
    for i in range(1, size):
        harmonic = (i+1)//2
        matrix[i][i] += RIDGE * max(1., (harmonic/2)**2)
    for i in range(size):
        pivot = max(range(i, size), key=lambda j: abs(matrix[j][i]))
        matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
        divisor = matrix[i][i]
        matrix[i] = [v/divisor for v in matrix[i]]
        for j in range(size):
            if j != i:
                factor = matrix[j][i]
                matrix[j] = [a - factor*b for a, b in zip(matrix[j], matrix[i])]
    return [round(row[-1], 4) for row in matrix]


def windows_for(runs):
    windows = []
    for run in runs:
        start = datetime.fromisoformat(run['start'])
        first = start.hour*3600 + start.minute*60
        last = first + run['duration']
        bins = run['bins']
        for beginning in range(first//BIN*BIN, last, BIN):
            exposure = min(last, beginning+BIN) - max(first+WARMUP, beginning)
            if exposure > 0:
                windows.append((beginning+BIN/2, exposure, bins.get(str(beginning), {})))
    return windows


def fit_order(windows, order):
    coefficients = {}
    edges = sorted({edge for _, _, counts in windows for edge in counts})
    for edge in edges:
        samples = [(second, counts.get(edge, 0)*3600/exposure, exposure/BIN)
                   for second, exposure, counts in windows]
        peak = fmean(rate for _, rate, _ in samples)
        prior = [(hour*3600, peak * multiplier, .18) for hour, multiplier in DAILY_PROFILE]
        coefficients[edge] = regress(samples + prior, order)
    return coefficients


def forecast_error(coefficients, windows):
    edges = sorted(set(coefficients) | {edge for _, _, counts in windows for edge in counts})
    absolute_error, observations = 0., 0.
    for second, seconds, counts in windows:
        exposure = seconds/3600
        for edge in edges:
            expected = predict(coefficients[edge], second)*exposure if edge in coefficients else 0.
            absolute_error += abs(expected-counts.get(edge, 0))
        observations += len(edges)*exposure
    return absolute_error/observations


def train(output=OUTPUT):
    runs = [read_json(file) for file in sorted(output.glob('*/*/treino/summary.json'))]
    if {run['peak'] for run in runs} != {'manha', 'tarde'}:
        raise ValueError('Conclua pelo menos um treino por pico antes de ajustar Fourier.')
    windows = windows_for(runs)
    validation = [read_json(file) for file in sorted(output.glob('*/*/validacao/summary.json'))]
    if validation and {run['peak'] for run in validation} != {'manha', 'tarde'}:
        raise ValueError('Conclua a validação dos dois picos antes de selecionar a ordem.')
    selected = 2
    report = {}
    if validation:
        validation_windows = windows_for(validation)
        fitted = {order: fit_order(windows, order) for order in ORDERS}
        errors = {order: forecast_error(model, validation_windows) for order, model in fitted.items()}
        selected = min(ORDERS, key=lambda order: (errors[order], order))
        coefficients = fitted[selected]
        report['validation'] = dict(seeds=sorted({run['seed'] for run in validation}),
                                    mae={str(order): value for order, value in errors.items()})
        print('MAE de validação (veíc./h): ' + ', '.join(f'ordem {k} = {v:.4f}' for k,v in errors.items()), flush=True)
    else:
        coefficients = fit_order(windows, selected)
    write_json(output/'fourier.json',
               dict(approaches=coefficients, harmonics=selected, period_h=24, bin_seconds=BIN,
                    training=[dict(peak=r['peak'], seed=r['seed'], source=r['source'],
                                   inputs=r['inputs']) for r in runs], **report))
    print(f'{len(coefficients)} aproximações ajustadas com {len(windows)} janelas de 15 min. Ordem {selected}.', flush=True)
