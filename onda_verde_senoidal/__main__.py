import argparse
from pathlib import Path

from .simulate import PROFILES, simulate


def main():
    cli = argparse.ArgumentParser(description='Onda verde senoidal no Quadrilátero de Curitiba')
    commands = cli.add_subparsers(dest='command', required=True)
    run = commands.add_parser('run', help='Executar um cenário no SUMO')
    run.add_argument('peak', choices=('manha', 'tarde'))
    run.add_argument('scenario', choices=('treino', 'validacao', 'referencia', 'otimizado', 'coordenado', 'revisado'))
    run.add_argument('--seed', type=int, required=True)
    run.add_argument('--source', type=Path)
    run.add_argument('--net', type=Path)
    run.add_argument('--signals', type=Path)
    run.add_argument('--broker', default='127.0.0.1:1885')
    fit = commands.add_parser('fit', help='Ajustar Fourier usando os cenários de treinamento')
    report = commands.add_parser('report', help='Consolidar os pares executados')
    batch = commands.add_parser('batch', help='Treinar e executar os dois picos com sementes pareadas')
    batch.add_argument('--seeds', type=int, nargs='+')
    batch.add_argument('--policies', nargs='+', choices=('otimizado', 'coordenado', 'revisado'), default=['coordenado'])
    batch.add_argument('--port', type=int, default=1886)
    serve = commands.add_parser('serve', help='Servir o painel local')
    serve.add_argument('--port', type=int, default=8077)
    for command in (run, fit, report, batch):
        command.add_argument('--profile', choices=tuple(PROFILES), default='original')
    serve.add_argument('--profile', choices=tuple(PROFILES))
    monitor = commands.add_parser('monitor', help='Reproduzir um ensaio e registrar as previsões por semáforo')
    monitor.add_argument('peak', choices=('manha', 'tarde'), default='manha', nargs='?')
    monitor.add_argument('--seed', type=int, default=101)
    monitor.add_argument('--policy', choices=('referencia', 'coordenado', 'otimizado'), default='coordenado')
    monitor.add_argument('--port', type=int, default=1891)
    monitor.add_argument('--duration', type=int, help='Limitar a duração simulada em segundos')
    broker = commands.add_parser('broker', help='Iniciar o broker MQTT 5 local')
    broker.add_argument('--port', type=int, default=1885)
    args = cli.parse_args()
    if args.command == 'run':
        simulate(args.peak, args.scenario, args.seed, source=args.source, net_path=args.net,
                 extra_plan=args.signals, broker=args.broker, profile=args.profile)
    elif args.command == 'fit':
        from .fourier import train
        train(PROFILES[args.profile])
    elif args.command == 'report':
        from .report import build_report
        build_report(PROFILES[args.profile])
    elif args.command == 'batch':
        from .batch import batch
        seeds = args.seeds or ([101] if args.profile == 'escalonado' else [42, 73])
        batch(tuple(dict.fromkeys(seeds)), args.port, tuple(dict.fromkeys(args.policies)), args.profile)
    elif args.command == 'monitor':
        from .live import run_monitor
        run_monitor(args.peak, args.seed, args.port, args.duration, args.policy)
    elif args.command == 'broker':
        import asyncio
        from mqttools.broker import Broker
        print(f'Broker MQTT 5 em 127.0.0.1:{args.port}', flush=True)
        asyncio.run(Broker([('127.0.0.1', args.port)]).serve_forever())
    else:
        from .server import serve_dashboard
        profile = args.profile or ('escalonado' if (PROFILES['escalonado']/'report.json').is_file() else 'original')
        serve_dashboard(args.port, PROFILES[profile])


if __name__ == '__main__':
    main()
