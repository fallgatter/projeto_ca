"""Local SUMO benchmark with a temporary loopback-only MQTT 5 broker."""
import asyncio
from pathlib import Path
import sys

from mqttools.broker import Broker


async def replay(peak, port, seed):
    run = f'kennedy-integrada-{peak}-mqtt-s{seed}'
    with Path(f'runs/{run}.console.log').open('w', encoding='utf-8') as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-X', 'utf8', '-m', 'ca', 'replay',
            f'mensal-2026-07-{peak}-20261119-235229-202742', '--name', run,
            '--control', 'mqtt-adaptive', '--signals', 'config/signals/onda-verde-kennedy.add.xml',
            '--summary-only', '--mqtt', f'127.0.0.1:{port}', '--sumo-seed', seed, stdout=log, stderr=log)
        return await process.wait()


async def main():
    broker = Broker(('127.0.0.1', 0))
    task = asyncio.create_task(broker.serve_forever())
    try:
        _, port = await asyncio.wait_for(broker.getsockname(), 5)
        seeds = sys.argv[1:] or ['42', '73']
        return any(await asyncio.gather(*(replay(peak, port, seed)
                   for peak in ['manha', 'tarde'] for seed in seeds)))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


raise SystemExit(asyncio.run(main()))
