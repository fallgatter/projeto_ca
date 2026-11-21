'use strict';

const $ = (id) => document.getElementById(id);
const variants = ['referencia', 'otimizado'];
const views = [$('before-map'), $('after-map')].map((canvas, index) => ({
  canvas, index, ctx: canvas.getContext('2d'), base: document.createElement('canvas'), cacheKey: ''
}));
const number = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
const integer = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
const coefficientFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 4 });
const contributionFormat = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3, signDisplay: 'exceptZero' });
const OBSERVED_WINDOW = 5;
const policyLabels = {coordenado: 'Preditivo coordenado', revisado: 'Preditivo revisado · 5 min',
  otimizado: 'Preditivo inicial'};
const state = {
  road: 'kennedy', pair: null, playing: false, time: 0, last: 0, scale: 1,
  dx: 0, dy: 0, selected: null, chunks: new Map(), inspectorKey: '', dataVersion: 0,
  drawKey: '', forecastKey: '', forecastRuns: new Map(), queueRuns: new Map(),
};
const shades = { green: '#66e6a5', yellow: '#ffd360', red: '#ff707e', unknown: '#637484' };

function isolated() {
  return state.road !== 'rede' && !$('isolate').disabled && $('isolate').checked;
}

function el(tag, text, cssClass) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cssClass) node.className = cssClass;
  return node;
}

function showProblem(message) {
  $('problem').textContent = message;
  $('problem').hidden = !message;
}

async function json(path) {
  const response = await fetch(path, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${path} (${response.status})`);
  return response.json();
}

function clock(seconds, short = false) {
  const hours = state.pair.start.slice(11, 16).split(':').map(Number);
  const absolute = Math.floor(seconds) + hours[0] * 3600 + hours[1] * 60;
  return [Math.floor(absolute / 3600) % 24, Math.floor(absolute / 60) % 60, absolute % 60]
    .slice(0, short ? 2 : 3).map((part) => String(part).padStart(2, '0')).join(':');
}

function prepareChunk(frames) {
  const events = [];
  let lights = {};
  const prepared = frames.map(([time, vehicles, delta, updates]) => {
    lights = { ...lights, ...delta };
    events.push(...updates);
    return { time, vehicles, lights, ids: new Map(vehicles.map((row) => [row[0], row])) };
  });
  return { events, frames: prepared };
}

function chunk(index, scenario) {
  if (index < 0 || index * state.report.chunk >= state.pair.duration) return undefined;
  const path = `${state.pair.scenarios[scenario].path}/${index}`;
  if (!state.chunks.has(path)) {
    const record = {};
    const run = state.pair;
    state.chunks.set(path, record);
    json(`/data/${path}.json`).then((data) => {
      record.data = prepareChunk(data);
      state.dataVersion++;
      if (state.pair === run) showProblem('');
    }).catch((error) => {
      if (state.pair === run) {
        showProblem(`Não foi possível carregar o trecho do replay (${error.message}).`);
        setPlaying(false);
      }
    });
    if (state.chunks.size > 18) state.chunks.delete(state.chunks.keys().next().value);
  }
  return state.chunks.get(path).data;
}

function timeline(scenario) {
  const step = state.report.chunk;
  const index = Math.max(0, Math.ceil(state.time / step) - 1);
  const current = chunk(index, scenario);
  const previous = chunk(index - 1, scenario);
  const next = chunk(index + 1, scenario);
  if (!current?.frames.length) return null;
  const frames = current.frames;
  const nextIndex = frames.findIndex((frame) => frame.time > state.time);
  const primary = nextIndex < 0 ? frames.at(-1) : frames[nextIndex - 1] || previous?.frames.at(-1) || frames[0];
  const following = nextIndex < 0 ? next?.frames[0] || primary : frames[nextIndex];
  const mix = Math.max(0, Math.min(1, (state.time - primary.time) / (following.time - primary.time || 1)));
  return { primary, following, mix, events: [...(previous?.events || []), ...current.events] };
}

function dimensions(canvas) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  const resolution = Math.min(2, window.devicePixelRatio || 1);
  const w = Math.round(width * resolution);
  const h = Math.round(height * resolution);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  return { width, height, resolution };
}

function transform(view) {
  const { width, height, resolution } = dimensions(view.canvas);
  const [left, bottom, right, top] = state.area.bounds;
  const scale = Math.min((width - 36) / (right - left), (height - 36) / (top - bottom)) * state.scale;
  const cx = (left + right) / 2 + state.dx;
  const cy = (bottom + top) / 2 + state.dy;
  return { width, height, resolution, scale,
    point: (x, y) => [width / 2 + (x - cx) * scale, height / 2 - (y - cy) * scale] };
}

function trace(ctx, coordinates, point) {
  coordinates.forEach(([x, y], i) => {
    const p = point(x, y);
    if (!i) ctx.moveTo(...p); else ctx.lineTo(...p);
  });
}

function drawBase(view, t) {
  const key = [state.road, isolated(), state.scale, state.dx, state.dy, view.canvas.width, view.canvas.height].join('/');
  if (view.cacheKey === key) return;
  view.cacheKey = key;
  view.base.width = view.canvas.width;
  view.base.height = view.canvas.height;
  const ctx = view.base.getContext('2d');
  ctx.setTransform(t.resolution, 0, 0, t.resolution, 0, 0);
  ctx.fillStyle = '#101922';
  ctx.fillRect(0, 0, t.width, t.height);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const [left, bottom] = t.point(state.map.bounds[0], state.map.bounds[1]);
  const size = t.scale * 500;
  ctx.strokeStyle = '#16242e';
  ctx.lineWidth = 1;
  ctx.beginPath();
  if (size > 13) {
    for (let x = left % size; x < t.width; x += size) { ctx.moveTo(x, 0); ctx.lineTo(x, t.height); }
    for (let y = bottom % size; y < t.height; y += size) { ctx.moveTo(0, y); ctx.lineTo(t.width, y); }
  }
  ctx.stroke();
  const roadColors = ['#3d5363', '#314553', '#263b4a', '#20323f'];
  for (let rank = isolated() ? -1 : 3; rank >= 0; rank--) {
    ctx.beginPath();
    for (const [type, shape] of state.map.roads) {
      if (rank === type) trace(ctx, shape, t.point);
    }
    ctx.strokeStyle = roadColors[rank];
    ctx.lineWidth = Math.min(4.2, (rank === 0 ? 1.7 : rank === 1 ? 1.4 : 1.0) * Math.sqrt(state.scale));
    ctx.stroke();
  }
  ctx.beginPath();
  for (const shape of state.area.shapes || []) trace(ctx, shape, t.point);
  ctx.strokeStyle = view.index === 0 ? '#5e83a0' : '#3e8c81';
  ctx.lineWidth = 2.5;
  ctx.stroke();
}

function lamps(lights, id, indexes) {
  const stateLetters = indexes.map((i) => lights[id]?.[i]);
  if (stateLetters.some((letter) => letter && 'gG'.includes(letter))) return 'green';
  if (stateLetters.some((letter) => letter && 'yYuU'.includes(letter))) return 'yellow';
  if (stateLetters.some((letter) => letter && 'rR'.includes(letter))) return 'red';
  return 'unknown';
}

function inFrame(x, y, t, margin = 0) {
  return x >= -margin && y >= -margin && x <= t.width + margin && y <= t.height + margin;
}

function drawTraffic(view, t, frame) {
  const { ctx } = view;
  let cars = 0, buses = 0;
  for (const [id, x, y, angle, isBus, stopped, mask] of frame.primary.vehicles) {
    if (isolated() && !(mask & state.report.masks[state.road])) continue;
    const match = frame.following.ids.get(id);
    const continuous = match && (!isolated() || (match[6] & state.report.masks[state.road])) &&
      Math.hypot(match[1] - x, match[2] - y) < 70;
    const [px, py] = t.point(
      continuous ? x + (match[1] - x) * frame.mix : x,
      continuous ? y + (match[2] - y) * frame.mix : y
    );
    if (!inFrame(px, py, t, 3)) continue;
    const length = isBus ? Math.max(7, Math.min(19, t.scale * 13)) : Math.max(3.2, Math.min(8, t.scale * 5));
    const width = isBus ? 3.4 : 2.5;
    ctx.save();
    ctx.translate(px, py);
    ctx.rotate(angle * Math.PI / 180);
    ctx.fillStyle = isBus ? (stopped ? '#ba8b54' : '#efb65d') : (stopped ? '#9fb3c3' : '#77c5ff');
    ctx.fillRect(-width / 2, -length / 2, width, length);
    if (isBus) {
      ctx.fillStyle = '#fff0ca';
      ctx.fillRect(-width / 2, -length / 2, width, 1.2);
      buses++;
    } else cars++;
    ctx.restore();
  }
  const counts = view.index ? $('after-count') : $('before-count');
  const label = `${integer.format(cars)} carros · ${integer.format(buses)} ônibus`;
  if (counts.textContent !== label) counts.textContent = label;
}

function drawLights(view, t, lights) {
  const { ctx } = view;
  for (const [id, info] of Object.entries(state.map.lights)) {
    const focused = state.area.signals.has(id);
    if (isolated() && !focused) continue;
    const selected = state.selected === id;
    const [x, y] = t.point(...info.point);
    if (!inFrame(x, y, t, 22)) continue;
    const laneLevel = t.scale > .72 || selected;
    const laneInfo = info.approaches.filter((lane) => lane[4].includes(state.road));
    const approaches = laneLevel ? (isolated() ? laneInfo : info.approaches) : [[...info.point,
      (laneInfo.length ? laneInfo : info.approaches).flatMap((row) => row[2])]];
    ctx.globalAlpha = focused || selected ? 1 : .55;
    for (const lane of approaches) {
      const [sx, sy] = t.point(lane[0], lane[1]);
      ctx.beginPath();
      ctx.arc(sx, sy, focused ? (laneLevel ? 2.5 : 3.4) : 1.8, 0, Math.PI * 2);
      ctx.fillStyle = shades[lamps(lights, id, lane[2])];
      ctx.fill();
      if (focused) { ctx.strokeStyle = '#101922'; ctx.lineWidth = .8; ctx.stroke(); }
    }
    if (selected) {
      ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.strokeStyle = '#f1f8fa'; ctx.lineWidth = 1; ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
}

function drawPackets(ctx, t, events) {
  let visible = 0;
  for (const event of events) {
    const age = state.time - event.s;
    if (event.kind !== 'mqtt' || age < 0 || age > 24) continue;
    const senderHere = state.area.signals.has(event.from), receiverHere = state.area.signals.has(event.to);
    if (isolated() ? !(senderHere && receiverHere) : !(senderHere || receiverHere)) continue;
    const origin = state.map.lights[event.from]?.point;
    const target = state.map.lights[event.to]?.point;
    if (!origin || !target) continue;
    const [x1, y1] = t.point(...origin);
    const [x2, y2] = t.point(...target);
    if (!inFrame(x1, y1, t, 30) && !inFrame(x2, y2, t, 30)) continue;
    const length = Math.hypot(x2-x1, y2-y1);
    if (length < 3) continue;
    visible++;
    const dx = (x2-x1)/length, dy = (y2-y1)/length;
    const bend = Math.min(26, Math.max(10, length*.2));
    const point = (p) => [x1+(x2-x1)*p-dy*bend*4*p*(1-p), y1+(y2-y1)*p+dx*bend*4*p*(1-p)];
    const focused = state.selected === event.from || state.selected === event.to;
    ctx.save();
    ctx.globalAlpha = Math.max(.3, 1-age/30)*(state.selected && !focused ? .55 : 1);
    ctx.strokeStyle = '#0d2630';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.quadraticCurveTo((x1+x2)/2-2*dy*bend, (y1+y2)/2+2*dx*bend, x2, y2);
    ctx.stroke();
    ctx.strokeStyle = '#72f5e0';
    ctx.lineWidth = focused ? 3 : 2;
    ctx.stroke();
    const [ax, ay] = point(.77), [bx, by] = point(.66);
    const direction = Math.atan2(ay-by, ax-bx);
    ctx.fillStyle = '#a6fff2';
    ctx.beginPath();
    ctx.moveTo(ax+Math.cos(direction)*5, ay+Math.sin(direction)*5);
    ctx.lineTo(ax+Math.cos(direction+2.5)*7, ay+Math.sin(direction+2.5)*7);
    ctx.lineTo(ax+Math.cos(direction-2.5)*7, ay+Math.sin(direction-2.5)*7);
    ctx.closePath(); ctx.fill();
    ctx.strokeStyle = '#a6fff2';
    ctx.lineWidth = 1.5;
    for (const [x, y, radius] of [[x1, y1, 6], [x2, y2, 8]]) {
      ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI*2); ctx.stroke();
    }
    const [px, py] = point(Math.min(1, age/10));
    ctx.shadowBlur = 9;
    ctx.shadowColor = '#7affec';
    ctx.beginPath(); ctx.arc(px, py, 4.5, 0, Math.PI*2); ctx.fill();
    ctx.restore();
  }
  if (visible) {
    ctx.fillStyle = '#102a31';
    ctx.fillRect(12, 12, 113, 26);
    ctx.fillStyle = '#a6fff2';
    ctx.font = '600 12px Segoe UI';
    ctx.fillText(`MQTT · ${visible} ${visible === 1 ? 'mensagem' : 'mensagens'}`, 19, 29);
  }
}

function drawMap(view, frame) {
  const t = transform(view);
  if (!t.width || !t.height) return;
  drawBase(view, t);
  const { ctx } = view;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.drawImage(view.base, 0, 0);
  ctx.setTransform(t.resolution, 0, 0, t.resolution, 0, 0);
  if (!frame) {
    ctx.fillStyle = '#b1c5ce';
    ctx.font = '14px Segoe UI';
    ctx.fillText('Carregando o trecho…', 14, 24);
    return;
  }
  drawTraffic(view, t, frame);
  drawLights(view, t, frame.primary.lights);
  if (view.index) drawPackets(ctx, t, frame.events);
  const meters = t.scale > .65 ? 100 : 500;
  ctx.fillStyle = '#c1d0d8';
  ctx.font = '12px Segoe UI';
  ctx.fillText(`${meters} m`, 13, t.height - 17);
  ctx.fillRect(13, t.height - 13, Math.max(1, meters * t.scale), 1.3);
}

function updateInspector(frames) {
  const panel = $('signal-detail');
  panel.hidden = !state.selected;
  if (!state.selected || frames.some((frame) => !frame)) return;
  const phases = frames.map((frame) => frame.primary.lights[state.selected]);
  const key = [state.selected, ...phases].join('/');
  updateSignalForecast();
  if (key === state.inspectorKey) return;
  state.inspectorKey = key;
  const info = state.map.lights[state.selected];
  const header = el('header');
  const close = el('button', 'Fechar');
  close.onclick = () => { state.selected = null; state.inspectorKey = ''; };
  header.append(el('strong', info.name), close);
  const rows = el('div', undefined, 'signal-approaches');
  const groups = new Map();
  for (const row of info.approaches) {
    if (isolated() && !row[4].includes(state.road)) continue;
    const road = row[3] || 'Aproximação sem nome';
    if (!groups.has(road)) groups.set(road, []);
    groups.get(road).push(...row[2]);
  }
  for (const [road, indexes] of groups) {
    const item = el('span', road);
    for (let j = 0; j < 2; j++) {
      const word = lamps(frames[j].primary.lights, state.selected, indexes);
      const lamp = el('i', '', 'lamp-dot');
      lamp.style.background = shades[word];
      const label = j ? 'depois' : 'antes';
      lamp.title = `${label}: ${{ green: 'verde', yellow: 'amarelo', red: 'vermelho', unknown: 'indefinido' }[word]}`;
      item.append(lamp, document.createTextNode(label));
    }
    rows.append(item);
  }
  $('signal-overview').replaceChildren(header, rows);
}

function updateMetrics() {
  const { scenarios } = state.pair;
  const [ref, opt] = variants.map((id) => scenarios[id]);
  if (ref.network.delay > 0) {
    const gain = 100*(1-opt.network.delay/ref.network.delay);
    const goal = gain >= 10 ? 'meta de 10% atingida' : 'abaixo da meta de 10% de redução';
    $('gain-note').textContent = `Atraso médio da malha · ${gain >= 0 ? 'redução' : 'aumento'} de ${number.format(Math.abs(gain))}% neste ensaio · ${goal}`;
  }
  const onNetwork = state.road === 'rede';
  const queue = queueRecord();
  const [before, after] = [ref, opt].map((run, i) => ({
    travel: onNetwork ? run.network.travel : run.visits?.[state.road]?.todos.time.mean,
    delay: run.network.delay,
    queue: queue.data?.[i]?.[state.road]
  }));
  const metrics = [
    ['travel', onNetwork ? 'Tempo médio de viagem' : 'Tempo médio na via', ' s'],
    ['delay', onNetwork ? 'Atraso médio por veículo' : 'Atraso médio por veículo na malha', ' s'],
    ['queue', 'Maior fila contínua', ' m']
  ];
  $('metrics-note').textContent = onNetwork
    ? `${integer.format(ref.network.pairs)} viagens comuns para tempo e atraso · referência → preditivo`
    : 'Tempo na via entre entrada e saída observadas · referência → preditivo';
  $('metrics').replaceChildren(...metrics.map(([key, label, unit]) => {
    const metric = el('div', undefined, 'metric');
    const a = before[key], b = after[key];
    const display = value => value == null ? '—' : number.format(value) + unit;
    metric.append(el('span', label), el('strong', `${display(a)} → ${display(b)}`));
    if (a > 0 && b != null) {
      const percent = 100*(b/a-1);
      const cls = percent < 0 ? 'improvement' : percent > 0 ? 'worse' : '';
      metric.append(el('span', `${percent > 0 ? '+' : ''}${number.format(percent)}%`, cls));
    } else if (key === 'queue' && (a == null || b == null)) {
      metric.append(el('span', queue.loading ? 'Carregando medição…' : 'Medição indisponível neste ensaio'));
    }
    return metric;
  }));
  $('policy-name').textContent = policyLabels[state.pair.policy] + ' + MQTT';
}

function queueRecord() {
  const pair = state.pair;
  if (!state.queueRuns.has(pair)) {
    const record = {loading: true};
    state.queueRuns.set(pair, record);
    const paths = variants.map(side => pair.scenarios[side].path);
    Promise.all(paths.map(path => json(`/data/${path}/queues.json`).catch(() => null))).then(data => {
      record.data = data;
      record.loading = false;
      if (state.pair === pair) updateMetrics();
    });
  }
  return state.queueRuns.get(pair);
}

function forecastRecord() {
  const path = state.pair.scenarios.otimizado.path;
  if (!state.forecastRuns.has(path)) {
    const record = {loading: true};
    state.forecastRuns.set(path, record);
    json(`/data/${path}/forecast.json`).then(history => { record.history = history; })
      .catch(() => { record.history = null; }).finally(() => {
        record.loading = false;
        state.dataVersion++;
      });
  }
  return state.forecastRuns.get(path);
}

function fourierTerms(coefficients, second) {
  const angle = 2*Math.PI * second/86400;
  const result = [coefficients[0]];
  for (let order = 1; order <= (coefficients.length-1)/2; order++) {
    result.push(coefficients[2*order-1]*Math.cos(order*angle) + coefficients[2*order]*Math.sin(order*angle));
  }
  return result;
}

function harmonicFlow(coefficients, second) {
  return Math.max(0, fourierTerms(coefficients, second).reduce((sum, term) => sum+term, 0));
}

function updateSignalForecast() {
  const select = $('signal-approach');
  const edges = new Map();
  for (const [, , , street, corridors, edge] of state.map.lights[state.selected].approaches) {
    if ((!isolated() || corridors.includes(state.road)) && state.coefficients?.[edge]) {
      edges.set(edge, street || 'Aproximação sem nome');
    }
  }
  const optionsKey = [state.selected, ...edges.keys()].join('/');
  if (optionsKey !== select.dataset.key) {
    select.dataset.key = optionsKey;
    select.replaceChildren(...Array.from(edges, ([edge, street]) => {
      const option = el('option', `${street} · ${edge}`);
      option.value = edge;
      return option;
    }));
  }
  const record = forecastRecord();
  const coefficients = state.coefficients?.[select.value];
  const canvas = $('signal-chart');
  select.disabled = !coefficients;
  canvas.hidden = !coefficients;
  const minute = Math.floor(state.time/60)*60;
  const key = [state.selected, state.pair.scenarios.otimizado.path, select.value, record.loading, minute,
    canvas.clientWidth, canvas.clientHeight, isolated()].join('/');
  if (state.forecastKey === key) return;
  state.forecastKey = key;
  const series = record.history?.approaches[select.value];
  $('legend-corrected').hidden = $('legend-observed').hidden = !series;
  $('signal-forecast-note').textContent = !coefficients ? 'Sem coeficientes de Fourier para esta aproximação.'
    : record.loading ? 'Carregando histórico do ensaio…'
    : !series ? 'Este replay tem a curva de Fourier disponível. O histórico de correção está indisponível.'
    : 'O traço observado mostra a média dos últimos 5 minutos de carros e ônibus. O eixo vertical usa log(1 + fluxo), com rótulos em veículos/h.';
  const elapsed = series?.filter(row => row[0] <= minute) || [];
  const recent = elapsed.at(-1);
  const observedAverage = elapsed.length >= OBSERVED_WINDOW
    ? elapsed.slice(-OBSERVED_WINDOW).reduce((total, row) => total+row[3], 0)/OBSERVED_WINDOW : null;
  $('signal-values').textContent = recent ? `${clock(recent[0], true)} · Fourier ${number.format(recent[1])} → ${number.format(recent[2])} veíc./h · ${minuteCount(recent)}` +
    (observedAverage == null ? '' : ` · média em 5 min ${number.format(observedAverage)} veíc./h`)
    : series ? 'Aguardando a primeira medição do ensaio.' : '';
  $('signal-model').hidden = !coefficients;
  if (!coefficients) return;
  const [hh, mm] = state.pair.start.slice(11, 16).split(':').map(Number);
  const absolute = hh*3600 + mm*60;
  const base = Array.from({length: 145}, (_, i) => [600*i, harmonicFlow(coefficients, 600*i+22.5)]);
  let observedTotal = 0;
  const visible = elapsed.map(([t, , corrected, observed], index) => {
    observedTotal += observed;
    if (index >= OBSERVED_WINDOW) observedTotal -= elapsed[index-OBSERVED_WINDOW][3];
    return [absolute+t, corrected, index+1 >= OBSERVED_WINDOW ? observedTotal/OBSERVED_WINDOW : null];
  });
  drawSignalChart(canvas, base, visible, absolute, minute);
  updateModelDiagram(coefficients, absolute, minute, elapsed, select.value, edges.get(select.value));
}

function minuteCount(row) {
  const modes = row[6];
  if (modes) {
    const [cars, buses] = modes;
    return `${cars} ${cars === 1 ? 'carro' : 'carros'} e ${buses} ônibus no último minuto`;
  }
  const total = row[3]/60;
  return `${total} ${total === 1 ? 'veículo' : 'veículos'} no último minuto`;
}

function updateModelDiagram(coefficients, absolute, minute, elapsed, edge, street) {
  const format = value => value == null ? '—' : coefficientFormat.format(value);
  const recent = elapsed.at(-1);
  const second = recent?.[0] ?? minute;
  const terms = fourierTerms(coefficients, absolute+second+22.5);
  let harmonicSum = 0;
  const components = terms.map((term, order) => {
    const from = harmonicSum;
    harmonicSum += term;
    return [order ? `Harmônico de ${number.format(24/order)} h` : 'Termo constante',
      from, harmonicSum, term, order ? 'harmonic' : 'constant'];
  });
  const nominal = recent?.[1] ?? Math.max(0, harmonicSum);
  const correction = recent?.[4];
  const corrected = recent?.[2];
  $('model-clock').textContent = `${clock(second, true)} · previsão para os próximos 45 segundos`;
  $('model-street').textContent = street;
  $('model-observed').textContent = recent ? minuteCount(recent) : 'Aguardando medição';
  drawJunction(edge);
  drawForecastBars([
    ...components,
    ['Previsão de Fourier', 0, nominal, nominal, 'baseline'],
    ['Correção do minuto', nominal, nominal+(correction ?? 0), correction, 'correction'],
    ['Previsão corrigida', 0, corrected ?? 0, corrected, 'corrected'],
  ]);
  const limit = $('model-limit');
  limit.hidden = harmonicSum >= 0 && nominal+(correction ?? 0) >= 0;
  limit.textContent = 'O modelo limita a previsão a zero quando a soma fica negativa.';
  $('model-order').textContent = String(terms.length-1);
  const subscript = '₀₁₂₃₄₅₆₇₈₉';
  $('model-coefficients').replaceChildren(...coefficients.map((value, index) => {
    const order = String(Math.ceil(index/2)).replace(/\d/g, digit => subscript[Number(digit)]);
    const label = (index === 0 || index % 2 === 1 ? 'a' : 'b') + order;
    const cell = el('div');
    cell.append(el('dt', label), el('dd', format(value)));
    return cell;
  }));
  const prior = elapsed.at(-2)?.[4] ?? 0;
  const review = recent?.[7];
  const withWindow = state.pair.policy === 'revisado';
  $('model-error-formula').textContent = withWindow
    ? 'erroₘ = (60/n) × sinal(O − E) × máx(0, |O − E| − 2√máx(1, E))'
    : 'erroₘ = fluxo observado − F(tₘ − 30)';
  $('model-window').hidden = !review;
  if (review) {
    const [n, observed, expected, tolerance] = review;
    $('model-window').textContent = `Em ${n} min, O = ${observed} veículos observados, E = ${format(expected)} esperados e tolerância = ${format(tolerance)} veículos.`;
  }
  const error = review ? format(review[4]) : recent?.length > 5 ? `${format(recent[3])} − ${format(recent[5])}` : null;
  $('model-current').textContent = error == null ? 'Aguardando medições do replay.'
    : `rₘ = 0,80 × (${format(prior)}) + 0,20 × (${error}) = ${format(recent[4])}`;
  $('model-result-operation').textContent = recent
    ? `máx(0, ${format(nominal)} + (${format(correction)})) = ${format(corrected)} veíc./h`
    : 'A previsão corrigida aparece após a primeira medição.';
}

function drawForecastBars(values) {
  const bounds = values.filter(([, , , value]) => value != null).flatMap(([, start, end]) => [start, end]);
  const low = Math.min(0, ...bounds);
  const high = Math.max(low === 0 ? 1 : 0, ...bounds);
  const range = high-low;
  const position = value => 100*(value-low)/range;
  const chart = $('model-bars');
  chart.style.setProperty('--zero', `${position(0)}%`);
  if (chart.children.length !== values.length) {
    chart.replaceChildren(...values.map(([label, , , , tone]) => {
      const row = el('li', undefined, `model-bar-row ${tone}`);
      const track = el('span', undefined, 'model-track');
      track.setAttribute('aria-hidden', 'true');
      track.append(el('i', undefined, 'model-bar'));
      row.append(el('span', label), track, el('strong'));
      return row;
    }));
  }
  values.forEach(([, start, end, value, tone], index) => {
    const row = chart.children[index];
    const [, track, amount] = row.children;
    const additive = tone === 'harmonic' || tone === 'correction';
    amount.textContent = value == null ? '—' : (additive ? contributionFormat : number).format(value);
    row.classList.toggle('negative', value < 0);
    const bar = track.firstElementChild;
    bar.hidden = value == null;
    bar.style.left = `${position(Math.min(start, end))}%`;
    bar.style.width = `${Math.abs(position(end)-position(start))}%`;
  });
  const labels = low < 0 && high > 0 && position(0) >= 15 && position(0) <= 85 ? [low, 0, high] : [low, high];
  $('model-axis').replaceChildren(...labels.map((value, i) => {
    const label = el('span', number.format(value), i === 0 ? 'axis-start' : i === labels.length-1 ? 'axis-end' : '');
    label.style.left = `${position(value)}%`;
    return label;
  }));
}

function drawJunction(edge) {
  const canvas = $('model-junction');
  const shape = state.map.approach_shapes?.[edge];
  canvas.hidden = !shape;
  $('model-map-note').hidden = !shape;
  if (!shape) return;
  const {width, height, resolution} = dimensions(canvas);
  if (!width || !height) return;
  const ctx = canvas.getContext('2d');
  const center = state.map.lights[state.selected].point;
  const scale = Math.min(width, height)/200;
  const project = (x, y) => [width/2+(x-center[0])*scale, height/2-(y-center[1])*scale];
  const local = ([x,y]) => Math.abs(x-center[0])*scale <= width/2+30 &&
    Math.abs(y-center[1])*scale <= height/2+30;
  ctx.setTransform(resolution, 0, 0, resolution, 0, 0);
  ctx.fillStyle = '#0b141c';
  ctx.fillRect(0, 0, width, height);
  ctx.lineCap = ctx.lineJoin = 'round';
  for (const [rank, road] of state.map.roads) {
    if (!road.some(local)) continue;
    ctx.beginPath(); trace(ctx, road, project);
    ctx.strokeStyle = rank < 2 ? '#304958' : '#253744';
    ctx.lineWidth = rank < 2 ? 5 : 2.5;
    ctx.stroke();
  }
  ctx.beginPath(); trace(ctx, shape, project);
  ctx.strokeStyle = '#173f42'; ctx.lineWidth = 12; ctx.stroke();
  ctx.strokeStyle = '#71e9ce'; ctx.lineWidth = 4; ctx.stroke();
  const points = shape.map(([x,y]) => project(x,y));
  const length = points.reduce((total, [x,y], index) => index === 0 ? total :
    total + Math.hypot(x-points[index-1][0], y-points[index-1][1]), 0);
  for (const distance of [Math.min(16, length/2), 43, 70]) drawApproachArrow(ctx, points, distance);
  const [stopX, stopY] = project(...shape.at(-1));
  ctx.beginPath(); ctx.arc(stopX, stopY, 7, 0, 2*Math.PI);
  ctx.fillStyle = '#0b141c'; ctx.fill();
  ctx.strokeStyle = '#d8fff5'; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = '#d8fff5'; ctx.font = '600 12px Segoe UI';
  ctx.fillText('Semáforo', Math.min(stopX+13, width-65), Math.max(stopY-9, 14));
  ctx.fillStyle = '#a3b6c3'; ctx.font = '11px Segoe UI';
  ctx.fillText('50 m', 12, height-15);
  ctx.fillRect(12, height-11, 50*scale, 1);
}

function drawApproachArrow(ctx, points, distance) {
  for (let index = points.length-1; index > 0; index--) {
    const [x,y] = points[index], [prevX,prevY] = points[index-1];
    const length = Math.hypot(x-prevX, y-prevY);
    if (length <= distance) {
      distance -= length;
      continue;
    }
    const dx = (x-prevX)/length, dy = (y-prevY)/length;
    const px = x-distance*dx, py = y-distance*dy;
    ctx.beginPath();
    ctx.moveTo(px-6*dx-4*dy, py-6*dy+4*dx);
    ctx.lineTo(px, py);
    ctx.lineTo(px-6*dx+4*dy, py-6*dy-4*dx);
    ctx.strokeStyle = '#effff9'; ctx.lineWidth = 2; ctx.stroke();
    break;
  }
}

function drawSignalChart(canvas, base, visible, absolute, minute) {
  const ctx = canvas.getContext('2d');
  const {width, height, resolution} = dimensions(canvas);
  if (!width || !height) return;
  const values = visible.flatMap(([, corrected, observed]) => [corrected, observed ?? 0]);
  const scale = Math.log1p(Math.max(1, ...base.map(([,y]) => y), ...values)*1.08);
  const x = (s) => 46+(width-59)*s/86400;
  const y = (v) => height-27-(height-45)*Math.log1p(v)/scale;
  ctx.setTransform(resolution, 0, 0, resolution, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = '#192c36';
  ctx.fillRect(x(absolute), 17, x(state.pair.duration)-x(0), height-44);
  ctx.font = '12px Segoe UI';
  ctx.fillStyle = '#a3b6c3';
  ctx.fillText('veíc./h', 2, 12);
  ctx.strokeStyle = '#2b4050';
  for (let i=0; i<=4; i++) {
    const value = Math.expm1(scale*i/4);
    ctx.beginPath(); ctx.moveTo(x(0), y(value)); ctx.lineTo(x(86400), y(value)); ctx.stroke();
    ctx.fillText(number.format(value), 3, y(value)+4);
  }
  for (let i=0; i<=4; i++) {
    ctx.fillText(`${String(i*6).padStart(2, '0')}h`, Math.min(width-28, x(i*21600)-11), height-7);
  }
  ctx.strokeStyle = '#c4d5e0';
  ctx.setLineDash([3,4]);
  ctx.beginPath(); ctx.moveTo(x(absolute+minute), 15); ctx.lineTo(x(absolute+minute), height-27); ctx.stroke();
  ctx.setLineDash([]);
  ctx.strokeStyle = '#83afda'; ctx.lineWidth = 1.6;
  ctx.beginPath(); trace(ctx, base, (s,v) => [x(s),y(v)]); ctx.stroke();
  ctx.strokeStyle = '#6ee8c1'; ctx.lineWidth = 2.7;
  ctx.beginPath(); trace(ctx, visible, (s,v) => [x(s),y(v)]); ctx.stroke();
  const measurements = visible.filter(([, , observed]) => observed != null);
  ctx.strokeStyle = '#f2c986'; ctx.lineWidth = 1.5;
  ctx.beginPath(); trace(ctx, measurements.map(([s,,v]) => [s,v]), (s,v) => [x(s),y(v)]); ctx.stroke();
  if (measurements.length) {
    const [s,,v] = measurements.at(-1);
    ctx.fillStyle = '#f2c986';
    ctx.beginPath(); ctx.arc(x(s), y(v), 3.5, 0, Math.PI*2); ctx.fill();
  }
  if (visible.length) {
    const [s,v] = visible.at(-1);
    ctx.fillStyle = '#6ee8c1';
    ctx.beginPath(); ctx.arc(x(s), y(v), 3.8, 0, Math.PI*2); ctx.fill();
  }
}

function setPlaying(playing) {
  state.playing = playing;
  $('play').replaceChildren(document.createTextNode(playing ? 'Ⅱ ' : '▶ '), el('span', playing ? 'Pausar' : 'Reproduzir'));
  $('play').setAttribute('aria-pressed', String(playing));
}

function tick(stamp) {
  const delta = Math.min((stamp - state.last) / 1000, .16);
  state.last = stamp;
  if (state.pair) {
    let frames = variants.map(timeline);
    if (state.playing && frames.every(Boolean)) {
      state.time = Math.min(state.pair.duration, state.time + delta * Number($('rate').value));
      if (state.time >= state.pair.duration) setPlaying(false);
      $('time').value = Math.floor(state.time);
      frames = variants.map(timeline);
    }
    const drawKey = [state.pair.peak, state.pair.seed, state.pair.policy, state.road, isolated(), state.time, state.selected,
      state.scale, state.dx, state.dy, state.dataVersion, window.innerWidth, window.innerHeight].join('/');
    if (drawKey !== state.drawKey) {
      state.drawKey = drawKey;
      $('clock').textContent = clock(state.time);
      views.forEach((view, i) => drawMap(view, frames[i]));
      updateInspector(frames);
    }
  }
  requestAnimationFrame(tick);
}

function switchRoad(road) {
  state.road = road;
  state.area = state.areas[road];
  $('isolate').disabled = road === 'rede' || !state.report.masks;
  if ($('isolate').disabled) $('isolate').checked = false;
  state.selected = null;
  state.scale = 1;
  state.dx = state.dy = 0;
  $('corridors').querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', button.dataset.road === road));
  updateMetrics();
}

function switchRun(index) {
  state.pair = state.runs[index];
  state.time = Math.min(900, Math.floor(state.pair.duration / 2));
  $('time').max = state.pair.duration;
  $('time').value = state.time;
  $('end-clock').textContent = clock(state.pair.duration, true);
  const date = state.pair.start.slice(0, 10).split('-').reverse().join('/');
  $('run-date').textContent = state.report.profile === 'escalonado'
    ? `${date} · demanda escalonada · Fourier de ordem ${state.report.model.harmonics}` : date;
  setPlaying(false);
  updateMetrics();
}

function attachMap(view) {
  const canvas = view.canvas;
  let drag;
  canvas.addEventListener('keydown', (event) => {
    const t = transform(view);
    const distance = 30 / t.scale;
    const pan = { ArrowLeft: [-distance, 0], ArrowRight: [distance, 0],
      ArrowUp: [0, distance], ArrowDown: [0, -distance] }[event.key];
    if (pan) {
      event.preventDefault();
      state.dx += pan[0];
      state.dy += pan[1];
    } else if (event.key === '+' || event.key === '-') {
      event.preventDefault();
      zoom(event.key === '+' ? 1.25 : 1 / 1.25);
    }
  });
  canvas.addEventListener('wheel', (event) => {
    event.preventDefault();
    zoom(event.deltaY < 0 ? 1.19 : 1/1.19);
  }, { passive: false });
  canvas.addEventListener('pointerdown', (event) => {
    if (!state.area) return;
    canvas.setPointerCapture(event.pointerId);
    drag = { x: event.clientX, y: event.clientY, dx: state.dx, dy: state.dy };
  });
  canvas.addEventListener('pointermove', (event) => {
    if (!drag) return;
    const t = transform(view);
    state.dx = drag.dx - (event.clientX - drag.x) / t.scale;
    state.dy = drag.dy + (event.clientY - drag.y) / t.scale;
  });
  canvas.addEventListener('pointerup', (event) => {
    if (!drag) return;
    if (Math.hypot(drag.x - event.clientX, drag.y - event.clientY) < 5) {
      const t = transform(view);
      const rect = canvas.getBoundingClientRect();
      let closest = 15;
      state.selected = null;
      for (const [id, info] of Object.entries(state.map.lights)) {
        if (isolated() && !state.area.signals.has(id)) continue;
        const [x, y] = t.point(...info.point);
        const distance = Math.hypot(x + rect.left - event.clientX, y + rect.top - event.clientY);
        if (distance < closest) { closest = distance; state.selected = id; }
      }
      state.inspectorKey = '';
      if (state.selected) {
        requestAnimationFrame(() => $('signal-detail').scrollIntoView({block: 'nearest', behavior: 'smooth'}));
      }
    }
    drag = null;
  });
  canvas.addEventListener('pointercancel', () => { drag = null; });
}

function zoom(factor) {
  state.scale = Math.max(.55, Math.min(8, state.scale * factor));
}

async function init() {
  $('play').disabled = true;
  try {
    const [map, report, model] = await Promise.all([
      json('/data/map.json'), json('/data/report.json'), json('/data/fourier.json').catch(() => null)
    ]);
    const runs = report.pairs.filter(run => run.seed === 101)
      .sort((a,b) => Number(b.policy === 'revisado')-Number(a.policy === 'revisado'));
    if (!runs.length) throw new Error('Nenhum par da semente 101 disponível.');
    Object.assign(state, {map, report, runs, coefficients: model?.approaches});
    if (report.profile === 'escalonado') $('rate').value = '1';
    state.areas = { ...state.map.corridors, rede: {
      name: 'Quadrilátero inteiro', bounds: state.map.bounds, signals: Object.keys(state.map.lights)
    }};
    const labels = { kennedy: 'Presidente Kennedy', sete: 'Sete de Setembro', floriano: 'Marechal Floriano', rede: 'Toda a malha' };
    for (const [road, area] of Object.entries(state.areas)) {
      area.signals = new Set(area.signals);
      const button = el('button', labels[road]);
      button.dataset.road = road;
      button.onclick = () => switchRoad(road);
      $('corridors').append(button);
    }
    runs.forEach((run, index) => {
      const option = el('option', `${run.peak === 'manha' ? 'Manhã' : 'Tarde'} · Semente ${run.seed} · ${policyLabels[run.policy]}`);
      option.value = index;
      $('run').append(option);
    });
    const featured = runs.findIndex(p => p.peak === 'manha');
    $('run').selectedIndex = Math.max(0, featured);
    switchRun($('run').selectedIndex);
    $('signal-approach').onchange = updateSignalForecast;
    switchRoad('kennedy');
    views.forEach(attachMap);
    $('run').onchange = () => switchRun(Number($('run').value));
    $('isolate').onchange = () => { state.selected = null; state.inspectorKey = ''; };
    $('time').oninput = () => { state.time = Number($('time').value); };
    $('play').onclick = () => {
      if (!state.playing && state.time >= state.pair.duration) state.time = 0;
      setPlaying(!state.playing);
    };
    $('zoom-out').onclick = () => zoom(1 / 1.25);
    $('zoom-in').onclick = () => zoom(1.25);
    $('reset').onclick = () => { state.scale = 1; state.dx = state.dy = 0; };
    $('play').disabled = false;
    requestAnimationFrame(tick);
  } catch (error) {
    showProblem(`Resultados indisponíveis. Execute a consolidação dos replays e recarregue o painel. ${error.message}`);
  }
}

init();
