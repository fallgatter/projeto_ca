import json
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data' / 'cache'
LOCAL = ZoneInfo('America/Sao_Paulo')
PRESETS = {'manha': ('06:30', '09:00'), 'tarde': ('17:00', '19:00')}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.part', delete=False) as temp:
        pending = Path(temp.name)
        try:
            temp.write(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))
        except Exception:
            temp.close()
            pending.unlink(missing_ok=True)
            raise
    try:
        pending.replace(path)
    finally:
        pending.unlink(missing_ok=True)


def utc(value):
    return value.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def window(day, preset, start=None, end=None):
    if bool(start) != bool(end):
        raise ValueError('Informe início e fim juntos.')
    start, end = (start, end) if start else PRESETS[preset]
    day = date.fromisoformat(day)
    begin, finish = (datetime.combine(day, time.fromisoformat(t), LOCAL) for t in (start, end))
    if finish <= begin:
        raise ValueError('O fim precisa ser posterior ao início no mesmo dia.')
    return begin, finish


def reference_dir(override=None):
    return Path(override or os.getenv('CA_REFERENCE_DIR') or ROOT.parent / 'Sumo-CAmbiente-main').resolve()


def sumo_binary(name):
    binary = shutil.which(name)
    if not binary and os.getenv('SUMO_HOME'):
        path = Path(os.environ['SUMO_HOME']) / 'bin' / (name + ('.exe' if os.name == 'nt' else ''))
        binary = str(path) if path.is_file() else None
    if not binary:
        raise ValueError(f'{name} indisponível. Instale o Eclipse SUMO e configure SUMO_HOME ou PATH.')
    return binary


def sumo_modules():
    tools = Path(os.getenv('SUMO_HOME') or Path(sumo_binary('sumo')).parent.parent) / 'tools'
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    import sumolib
    import traci
    return sumolib, traci


def envelope(kind, **fields):
    return {'schema_version': '1.0', 'kind': kind, **fields}
