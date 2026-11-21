from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import run
import sys
from xml.etree.ElementTree import parse

from ca.io import sumo_modules, sumo_binary


plan = Path(sys.argv[1]).resolve()
suffix = sys.argv[2]
peaks = sys.argv[3:]
source = Path('runs/m4-manha-fixed/baseline.sumocfg').resolve()
traci = sumo_modules()[1]
traci.start([sumo_binary('sumo'), '-c', str(source), '--additional-files', str(plan),
             '--tripinfo-output', str(Path(f'runs/onda-{suffix}-smoke.trips.xml').resolve()),
             '--no-step-log', 'true'], numRetries=3)
try:
    for logic in parse(plan).getroot().findall('tlLogic'):
        signal = logic.get('id')
        offset = int(logic.get('offset'))
        times = [int(float(p.get('duration'))) for p in logic]
        position = (-offset) % sum(times)
        for phase, dur in enumerate(times):
            if position < dur:
                break
            position -= dur
        assert traci.trafficlight.getProgram(signal) == logic.get('programID'), signal
        assert traci.trafficlight.getPhase(signal) == phase, (signal, phase, traci.trafficlight.getPhase(signal))
        assert traci.trafficlight.getNextSwitch(signal) == dur - position, (signal, dur - position, traci.trafficlight.getNextSwitch(signal))
    print(f'Programas e offsets de {plan.name} confirmados via TraCI.', flush=True)
finally:
    traci.close()


def execute(peak):
    source_run = f'mensal-2026-07-{peak}-20261119-235229-202742'
    name = f'onda-{peak}-{suffix}'
    with Path(f'runs/{name}.console.log').open('w', encoding='utf-8') as output:
        result = run([sys.executable, '-X', 'utf8', '-m', 'ca', 'replay', source_run, '--name', name,
                      '--control', 'fixed', '--signals', str(plan), '--summary-only'], stdout=output, stderr=output)
    print(name, result.returncode, flush=True)
    return result.returncode


with ThreadPoolExecutor(max_workers=len(peaks)) as pool:
    status = list(pool.map(execute, peaks))
raise SystemExit(any(status))
