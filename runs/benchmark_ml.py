from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import run
import sys


def execute(peak, strategy):
    training = strategy == 'ml'
    model = Path(f'config/models/curitiba-{peak}.json')
    training_source = f'mensal-2026-07-{peak}-20261119-000410-273288'
    evaluation_source = f'mensal-2026-07-{peak}-20261119-235229-202742'
    if training:
        name = f'treino-{peak}-ml'
        code = replay(training_source, name, strategy, ['--train'])
        if code:
            return code
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes((Path('runs')/name/'signal-model.json').read_bytes())
    name = f'apr-{peak}-{strategy}'
    return replay(evaluation_source, name, strategy, [])


def replay(source, name, strategy, options):
    wave = 'config/signals/onda-verde-kennedy.add.xml'
    with Path(f'runs/{name}.console.log').open('w', encoding='utf-8') as log:
        result = run([sys.executable, '-X', 'utf8', '-m', 'ca', 'replay', source, '--name', name,
                      '--control', strategy, '--signals', wave, '--summary-only', *options], stdout=log, stderr=log)
    print(name, result.returncode, flush=True)
    return result.returncode


jobs = [(p, strategy) for p in ('manha', 'tarde') for strategy in ('ml', 'cycle-pressure', 'by-peak')]
with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
    results = list(pool.map(lambda job: execute(*job), jobs))
raise SystemExit(any(results))
