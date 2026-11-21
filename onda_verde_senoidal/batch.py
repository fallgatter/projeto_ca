from concurrent.futures import ThreadPoolExecutor
from subprocess import run
from sys import executable

from .io import ROOT

from .simulate import PROFILES


def batch(seeds, port, policies=('coordenado',), profile='original'):
    from mqttools.broker import BrokerThread

    output = PROFILES[profile]
    output.mkdir(parents=True, exist_ok=True)

    def execute(peak, scenario, seed):
        name = f'{peak}-{scenario}-{seed}'
        log = output / f'{name}.log'
        args = [executable, '-m', 'onda_verde_senoidal', 'run', peak, scenario,
                '--seed', str(seed), '--broker', f'127.0.0.1:{port}', '--profile', profile]
        if (output/peak/str(seed)/scenario/'summary.json').is_file():
            print(f'{name} já está concluído.', flush=True)
            return
        with log.open('w', encoding='utf-8') as stream:
            result = run(args, cwd=ROOT, stdout=stream, stderr=stream, check=False)
        if result.returncode:
            raise RuntimeError(f'Falha em {name}: {log}')
        print(f'{name} concluído.', flush=True)

    peaks = ('manha', 'tarde')
    with ThreadPoolExecutor(max_workers=6) as pool:
        training = [pool.submit(execute, peak, 'treino', 17) for peak in peaks]
        if profile == 'escalonado':
            training.extend(pool.submit(execute, peak, 'validacao', 73) for peak in peaks)
        references = [pool.submit(execute, peak, 'referencia', seed) for seed in seeds for peak in peaks]
        for future in training:
            future.result()
        from .fourier import train
        train(output)
        broker = BrokerThread([('127.0.0.1', port)])
        broker.start()
        try:
            predictions = [pool.submit(execute, peak, policy, seed)
                           for seed in seeds for peak in peaks for policy in policies]
            for future in references + predictions:
                future.result()
        finally:
            broker.stop()
    from .report import build_report
    build_report(output)
