import json
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event
from typing import Protocol

from .io import envelope


@dataclass(frozen=True)
class ExtendGreen:
    signal_id: str
    phase_index: int
    seconds: int


class SignalController(Protocol):
    def decide(self, observation: dict) -> list[ExtendGreen]: ...


class FixedProgram:
    def decide(self, observation):
        return []


def apply_extensions(traci, commands, remaining_budget):
    now = traci.simulation.getTime()
    tls = traci.trafficlight
    for command in commands:
        signal = command.signal_id
        if signal not in remaining_budget or type(command.seconds) is not int:
            raise ValueError('Comando semafórico inválido.')
        phase, budget = remaining_budget[signal]
        if phase != command.phase_index or tls.getPhase(signal) != phase or not 0 < command.seconds <= budget:
            raise ValueError('Extensão acima do orçamento ou fase divergente.')
        state = tls.getRedYellowGreenState(signal)
        if not any(c in 'Gg' for c in state) or any(c in 'yYuU' for c in state):
            raise ValueError('Apenas o verde estável pode ser estendido.')
        remaining = tls.getNextSwitch(signal) - now
        tls.setPhaseDuration(signal, max(0, remaining) + command.seconds)
        remaining_budget[signal] = phase, budget - command.seconds


def mqtt_endpoint(address, run, strategy, accept_commands):
    if strategy == 'mqtt-adaptive':
        from .mqtt_feedback import MqttLoop
        if not address or accept_commands:
            raise ValueError('mqtt-adaptive exige --mqtt e já inclui o controlador.')
        return MqttLoop(address, run)
    return MqttSensors(address, run, accept_commands) if address else None


class MqttSensors:
    def __init__(self, address, run=None, accept_commands=False):
        from paho.mqtt.client import CallbackAPIVersion, Client

        self.topic = f'curitiba/v1/{run}'
        self.run = run
        self.requests = Queue(maxsize=256)
        self.ready = Event()
        self.accept_commands = accept_commands
        self.client = Client(CallbackAPIVersion.VERSION2)
        self.client.max_queued_messages_set(8192)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        host, _, port = address.partition(':')
        if accept_commands and (not run or host not in ('localhost', '127.0.0.1')):
            raise ValueError('A recepção de comandos MQTT exige um identificador de execução e um broker local.')
        self.client.connect(host, int(port or 1883))
        self.client.loop_start()
        if not self.ready.wait(5):
            self.close()
            raise ValueError(f'O broker MQTT {address} não confirmou a conexão ou assinatura.')

    def on_connect(self, client, user_data, flags, code, properties):
        if code.is_failure:
            return
        if self.accept_commands:
            client.subscribe(f'{self.topic}/control/extend-green', qos=1)
        else:
            self.ready.set()

    def on_subscribe(self, client, user_data, mid, codes, properties):
        if not any(code.is_failure for code in codes):
            self.ready.set()

    def on_message(self, client, user_data, message):
        if message.retain or len(message.payload) > 4096:
            return
        try:
            data = json.loads(message.payload)
            if (isinstance(data, dict) and data.get('schema_version') == '1.0'
                    and data.get('kind') == 'signal.extend_green' and data.get('run_id') == self.run
                    and isinstance(data.get('signal_id'), str)
                    and type(data.get('phase_index')) is int and data['phase_index'] >= 0
                    and type(data.get('seconds')) is int and 1 <= data['seconds'] <= 5
                    and type(data.get('observed_s')) is int and 0 <= data['observed_s']
                    and type(data.get('next_switch_s')) in (int, float)
                    and data['observed_s'] < data['next_switch_s'] <= data['observed_s'] + 240):
                self.requests.put_nowait(data)
        except (ValueError, Full):
            pass

    def drain(self):
        for _ in range(256):
            try:
                yield self.requests.get_nowait()
            except Empty:
                return

    def publish(self, frame, run, nodes):
        for node_id, node in nodes.items():
            state = frame['intersections'].get(node_id, {})
            occupancy = {s['sensor_id']: s for s in state.get('sensors', [])}
            sensors = [occupancy.get(key, {'sensor_id': key, 'state': 'free', 'vehicle_speed_kmh': None})
                       for key in node['sensors']]
            packet = envelope('intersection.sensors', timestamp=frame['timestamp'], run_id=run,
                              observed_s=frame['end_s'], intersection_id=node_id, sensors=sensors,
                              instantaneous_metrics={'queue_length_meters': state.get('queue_now_m', 0),
                                                     'co2_grams_per_second': state.get('co2_now_g_s', 0.)},
                              signals={signal: frame['signals'][signal] for signal in node['signal_ids']})
            self.client.publish(f'curitiba/v1/{run}/intersections/{node_id}/sensors',
                                json.dumps(packet, allow_nan=False), qos=1)

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()
