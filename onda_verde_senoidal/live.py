from uuid import uuid4

from .io import read_json, write_json

from .fourier import predict
from .simulate import OUTPUT, WARMUP, simulate


LIVE = OUTPUT/'live'


class ForecastRecorder:
    def __init__(self, peak, seed, folder=None):
        self.folder = folder if folder is not None else LIVE/uuid4().hex
        self.peak = peak
        self.seed = seed
        self.histories = {}
        self.decisions = {}

    def sample(self, second, controller):
        from .control import UPDATE

        if second % UPDATE == 0:
            self.record_minute(second, controller)

    def record_minute(self, second, controller):
        from .control import HORIZON

        for edge, observed in controller.measurements.items():
            coef = controller.fourier[edge]
            nominal = predict(coef, controller.start+second+HORIZON/2)
            self.histories.setdefault(edge, []).append([
                second, nominal, controller.rate[edge]*3600, observed, controller.residual[edge],
                predict(coef, controller.start+second-30),
                controller.measurements_by_mode[edge], controller.flow_corrections.get(edge)
            ])
        for signal, decision in controller.diagnostics.items():
            sequence = self.decisions.setdefault(signal, [])
            if not sequence or decision['second'] != sequence[-1]['second']:
                sequence.append(decision)

    def attach_history(self, policy):
        peak, seed = self.peak, self.seed
        archived = OUTPUT/peak/str(seed)/policy
        if not (archived/'summary.json').is_file():
            return
        expected = read_json(archived/'summary.json')
        actual = read_json(self.folder/'summary.json')
        keys = ('inputs', 'start', 'duration', 'backend', 'network', 'corridors')
        same = all(expected[key] == actual[key] for key in keys)
        if policy != 'referencia':
            same &= all(expected['control'][key] == actual['control'][key]
                        for key in ('changes', 'forecasts', 'delivered', 'published', 'model'))
        if same and read_json(archived/'completed.json') == read_json(self.folder/'completed.json'):
            write_json(archived/'queues.json', read_json(self.folder/'queues.json'))
            if policy != 'referencia':
                self.write(archived)
            print(f'Indicadores registrados em {peak}/{seed}/{policy}.', flush=True)
        else:
            print('A execução monitorada divergiu do replay arquivado.', flush=True)

    def write(self, folder):
        write_json(folder/'forecast.json', {'approaches': self.histories, 'decisions': self.decisions})


def run_monitor(peak, seed, port, duration, policy='coordenado'):
    if duration is not None and duration <= WARMUP:
        raise ValueError(f'Use duração superior a {WARMUP} segundos para observar ajustes de verde.')
    monitor = ForecastRecorder(peak, seed)
    broker = None
    if policy != 'referencia':
        from mqttools.broker import BrokerThread

        broker = BrokerThread([('127.0.0.1', port)])
        broker.start()
    try:
        simulate(peak, policy, seed, broker=f'127.0.0.1:{port}', duration=duration, monitor=monitor)
        if duration is None:
            monitor.attach_history(policy)
    finally:
        if broker:
            broker.stop()
