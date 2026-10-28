import React, { useEffect, useMemo, useRef, useState } from 'react';
import { designApi } from '../api/design';
import ScientificPlot from './ScientificPlot';
import './OpticalAnalysis.css';

const number = (value, digits = 6) => value == null ? '∞' : Number(value).toLocaleString('en-US', { maximumFractionDigits: digits, useGrouping: false });
const colors = ['#76d9d0', '#9cabff', '#e4b779', '#d995df', '#fa8989', '#dce5ef'];
const csvCell = value => `"${String(value ?? 'Infinity').replaceAll('"', '""')}"`;
function downloadCsv(data, filename, scanning) {
  const meta = [['LaserClaw ABCD optical analysis', filename], ['mode', data.mode], ['wavelength_nm', data.wavelength_nm], ['effective_wavelength_nm', data.effective_wavelength_nm], ['output_gap_mm', data.output_gap_mm], ['thermal_f_mm', data.thermal_f_mm], ['beam_width_definition', '1/e^2 intensity radius'], ['model', data.planes], ...data.notes.map(note => ['note', note])];
  const keys = ['z_mm', 'w_mm', 'R_mm', 'inverse_R_per_mm', 'q_real_mm', 'q_imag_mm', 'n', 'segment'];
  const rows = scanning ? [['gap_mm', ...data.scan.series.map(s => `m_f_${s.f_mm ?? 'cold'}_mm`)], ...data.scan.series[0].points.map((p, i) => [p.gap_mm, ...data.scan.series.map(s => s.points[i].m)])] : [keys, ...data.trace.points.map(p => keys.map(k => p[k]))];
  const url = URL.createObjectURL(new Blob(['\uFEFF' + [...meta, [], ...rows].map(row => row.map(csvCell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a'); a.href = url; a.download = `${filename}.csv`; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function makePlot(data, view, unit, diameter, window, probeZ, gap, pan, identity) {
  const scanning = view === 'stability', factor = (unit === 'um' ? 1000 : 1) * (diameter ? 2 : 1);
  const widthPlot = ['radius', 'envelope'].includes(view);
  const value = p => view === 'inverse' ? p.inverse_R_per_mm : view === 'curvature' ? p.R_mm : p.w_mm * factor;
  const xRange = scanning ? data.scan.range_mm : window;
  const traces = [], shapes = [], annotations = [];
  const traceFor = (trace, label, color, reference = false) => {
    if (!trace?.points.length) return;
    // Separate R branches at every waist. Never draw a line through infinity.
    const x = [], y = [];
    trace.points.forEach((p, index) => {
      const before = trace.points[index - 1];
      if (view === 'curvature' && before?.segment === p.segment && before.q_real_mm * p.q_real_mm < 0) { x.push(null); y.push(null); }
      x.push(p.z_mm); y.push(value(p));
    });
    traces.push({ type: 'scatter', mode: 'lines', x, y, name: label, connectgaps: false, line: { color, width: reference ? 1.5 : 2.5, dash: reference ? 'dash' : 'solid', simplify: false }, hovertemplate: 'z = %{x:.6f} mm<br>%{y:.6g}<extra>%{fullData.name}</extra>' });
    if (view === 'envelope') traces.push({ type: 'scatter', mode: 'lines', x, y: y.map(v => v == null ? null : -v), name: label, showlegend: false, line: { color, width: reference ? 1 : 2, dash: reference ? 'dash' : 'solid', simplify: false }, hoverinfo: 'skip' });
    if (!reference && widthPlot && trace.waists.length) traces.push({ type: 'scatter', mode: 'markers', x: trace.waists.map(p => p.z_mm), y: trace.waists.map(value), name: '解析束腰', marker: { color: '#ffcf88', size: 9, symbol: 'diamond', line: { color: '#111b29', width: 1 } }, hovertemplate: '束腰 z = %{x:.8f} mm<br>%{y:.6g}<extra>解析极值</extra>' });
  };
  if (scanning) {
    data.scan.series.forEach((s, i) => traces.push({ type: 'scatter', mode: 'lines', x: s.points.map(p => p.gap_mm), y: s.points.map(p => p.m), name: s.f_mm == null ? '冷腔' : `f热 ${s.f_mm} mm`, line: { color: colors[i % colors.length], width: s.f_mm === data.thermal_f_mm ? 2.8 : 1.5 }, hovertemplate: 'd₂ = %{x:.6f} mm<br>m = %{y:.8f}<extra>%{fullData.name}</extra>' }));
    shapes.push({ type: 'rect', xref: 'paper', x0: 0, x1: 1, y0: -1, y1: 1, fillcolor: '#76d9d011', line: { width: 0 }, layer: 'below' });
    [-1, 1].forEach(y => shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: y, y1: y, line: { color: '#dcb778', width: 1, dash: 'dash' } }));
  } else {
    traceFor(data.cold_reference, '冷腔参考', '#8e9cac', true);
    traceFor(data.trace, data.mode === 'pump' ? '泵浦 · 等效 M² 场景' : data.thermal_f_mm == null ? '冷腔 · T = S' : `热腔 f=${data.thermal_f_mm} mm · T = S`, data.mode === 'pump' ? '#e4b779' : colors[0]);
    const addRegion = (start, end, color) => shapes.push({ type: 'rect', x0: start, x1: end, yref: 'paper', y0: 0, y1: 1, fillcolor: color, line: { width: 0 }, layer: 'below' });
    addRegion(data.crystal.position_mm, data.crystal.position_mm + data.crystal.thickness_mm, '#6c91ba12');
    addRegion(data.active_start_mm, data.active_end_mm, '#77c49d18');
    const visibleMarkers = data.markers.filter(m => m.z_mm >= xRange[0] && m.z_mm <= xRange[1]);
    visibleMarkers.forEach((m, i) => {
      shapes.push({ type: 'line', x0: m.z_mm, x1: m.z_mm, yref: 'paper', y0: 0, y1: 1, line: { color: m.kind === 'active' ? '#7caa944d' : '#b3c4d066', width: 1, dash: m.kind === 'mirror' ? 'solid' : 'dot' }, layer: 'below' });
      annotations.push({ x: m.z_mm, yref: 'paper', y: i % 2 ? 1.085 : 1.02, text: m.label, showarrow: false, font: { size: 10, color: '#adbdcf' }, xanchor: i === 0 ? 'left' : i === visibleMarkers.length - 1 ? 'right' : 'center' });
    });
  }
  const cursor = scanning ? gap : probeZ;
  if (Number.isFinite(cursor)) shapes.push({ type: 'line', x0: cursor, x1: cursor, yref: 'paper', y0: 0, y1: 1, line: { color: '#eef5faaa', width: 1, dash: 'dash' } });
  let yRange;
  if (scanning) yRange = [-1.5, 1.5]; // Display range only: all raw m values remain in traces and CSV.
  else {
    const ys = traces.flatMap(t => t.y.filter((v, i) => v != null && Number.isFinite(v) && t.x[i] >= xRange[0] && t.x[i] <= xRange[1]));
    if (ys.length) {
      const low = Math.min(...ys), high = Math.max(...ys), pad = Math.max((high - low) * .12, Math.abs(high) * .015, 1e-9);
      yRange = [view === 'radius' ? Math.max(0, low - pad) : low - pad, high + pad];
    }
  }
  const axis = { gridcolor: '#9aabc21c', zerolinecolor: '#98adc247', linecolor: '#637388', showline: true, mirror: true, ticks: 'outside', ticklen: 5, tickfont: { size: 11 }, showspikes: true, spikecolor: '#d4e4f1aa', spikethickness: 1, spikedash: 'dot', spikemode: 'across', exponentformat: 'power', automargin: true };
  return { data: traces, layout: {
    autosize: true, paper_bgcolor: '#101925', plot_bgcolor: '#101925', font: { color: '#b7c8db', family: 'Segoe UI, Microsoft YaHei, sans-serif', size: 12 },
    title: { text: `λ = ${data.wavelength_nm} nm · ${data.mode === 'pump' ? '等效 M² 泵浦场景' : `d₂ = ${data.output_gap_mm} mm · ${data.thermal_f_mm == null ? '冷腔' : `f热 = ${data.thermal_f_mm} mm`}`} · T = S`, x: .04, y: .98, xanchor: 'left', font: { size: 11, color: '#93aec2' } },
    margin: { l: 78, r: 25, t: 72, b: 94 }, dragmode: pan ? 'pan' : 'zoom', hovermode: 'closest', shapes, annotations,
    xaxis: { ...axis, title: { text: scanning ? '晶体后端面 → M2 · d₂ / mm' : '物理位置 z / mm · M1 = 0', standoff: 16 }, range: xRange },
    yaxis: { ...axis, title: { text: scanning ? 'm = (A + D) / 2' : view === 'inverse' ? '波前曲率 1/R / mm⁻¹' : view === 'curvature' ? '波前曲率半径 R / mm' : `${diameter ? '直径 2w' : '半径 w'} / ${unit === 'um' ? 'μm' : 'mm'} · 1/e² 强度`, standoff: 14 }, range: yRange, autorange: !yRange },
    legend: { orientation: 'h', x: 0, y: -.21, font: { size: 11 } }, uirevision: identity,
  } };
}

export default function OpticalAnalysis({ caseId, revisionId, revisionNumber, candidate, busy, onAdoptGap }) {
  const savedGap = candidate.length_mm - candidate.crystal.position_mm - candidate.crystal.thickness_mm;
  const [mode, setMode] = useState('cavity'), [view, setView] = useState('radius');
  const [gap, setGap] = useState(savedGap), [heat, setHeat] = useState(''), [samples, setSamples] = useState(900);
  const [unit, setUnit] = useState('um'), [diameter, setDiameter] = useState(false), [pan, setPan] = useState(false);
  const [extent, setExtent] = useState('all'), [customRange, setCustomRange] = useState(['', '']);
  const [expanded, setExpanded] = useState(false), [result, setResult] = useState(null), [error, setError] = useState('');
  const [cursor, setCursor] = useState(candidate.active_center_mm), [probeResult, setProbeResult] = useState(null);
  const [detail, setDetail] = useState('points'), [page, setPage] = useState(0);
  const plot = useRef(null), section = useRef(null);
  const params = useMemo(() => ({ candidate: candidate.rank, mode, output_gap_mm: mode === 'pump' ? savedGap : Number(gap), thermal_f_mm: mode === 'pump' || heat === '' ? null : Number(heat), samples: Number(samples) }), [candidate.rank, mode, gap, heat, samples, savedGap]);
  const requestKey = JSON.stringify(params), valid = mode === 'pump' || (gap !== '' && params.output_gap_mm >= .001 && params.output_gap_mm <= 2000);
  const data = result?.key === requestKey ? result.data : null;
  useEffect(() => {
    if (!valid) return;
    let alive = true;
    const timer = setTimeout(() => {
      setError('');
      designApi.analyze(caseId, revisionId, params).then(response => { if (alive) { setResult({ key: requestKey, data: response }); setPage(0); } }).catch(err => { if (alive) setError(err.message); });
    }, 220);
    return () => { alive = false; clearTimeout(timer); };
  }, [caseId, revisionId, requestKey, valid]);
  const probeKey = `${requestKey}:${cursor}`;
  const point = probeResult?.key === probeKey ? probeResult.point : null;
  useEffect(() => {
    if (!data?.trace.points.length || cursor === '' || Number(cursor) < data.z_range_mm[0] || Number(cursor) > data.z_range_mm[1]) return;
    let alive = true;
    const timer = setTimeout(() => {
      designApi.probe(caseId, revisionId, { ...params, z_mm: Number(cursor) }).then(response => { if (alive) setProbeResult({ key: probeKey, point: response.point }); }).catch(err => { if (alive) setError(err.message); });
    }, 160);
    return () => { alive = false; clearTimeout(timer); };
  }, [data, probeKey]);
  useEffect(() => {
    if (!expanded) return;
    const oldOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const escape = e => { if (e.key === 'Escape') setExpanded(false); };
    const trap = e => {
      if (e.key !== 'Tab') return;
      const items = [...section.current.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex="0"]')].filter(el => el.getClientRects().length);
      const first = items[0], last = items.at(-1);
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
    };
    const previous = document.activeElement;
    section.current.querySelector('button')?.focus();
    window.addEventListener('keydown', escape); window.addEventListener('keydown', trap);
    return () => { document.body.style.overflow = oldOverflow; window.removeEventListener('keydown', escape); window.removeEventListener('keydown', trap); previous?.focus(); };
  }, [expanded]);
  const range = useMemo(() => {
    if (!data) return [0, candidate.length_mm];
    if (extent === 'crystal') return [data.crystal.position_mm, data.crystal.position_mm + data.crystal.thickness_mm];
    if (extent === 'active') return [data.active_start_mm, data.active_end_mm];
    if (extent === 'focus') {
      const crystalWaists = data.trace.waists.filter(p => p.z_mm >= data.crystal.position_mm && p.z_mm <= data.crystal.position_mm + data.crystal.thickness_mm);
      const z = (mode === 'pump' ? crystalWaists.sort((a, b) => a.w_mm - b.w_mm)[0]?.z_mm : data.trace.minimum?.z_mm) ?? candidate.active_center_mm;
      return [Math.max(data.z_range_mm[0], z - 2), Math.min(data.z_range_mm[1], z + 2)];
    }
    if (extent === 'custom' && customRange.every(v => v !== '' && Number.isFinite(Number(v))) && Number(customRange[1]) > Number(customRange[0])) return customRange.map(Number);
    return data.z_range_mm;
  }, [data, extent, customRange, candidate, mode]);
  const identity = `${requestKey}-${view}-${unit}-${diameter}-${range.join(',')}-${expanded}`;
  const figure = useMemo(() => data ? makePlot(data, view, unit, diameter, range, cursor === '' ? null : Number(cursor), Number(gap), pan, identity) : null, [data, view, unit, diameter, range, cursor, gap, pan, identity]);
  const scanning = view === 'stability', filename = `design-${revisionId}-c${candidate.rank}-${mode}-${view}-d${params.output_gap_mm}-f${params.thermal_f_mm ?? 'cold'}`;
  const selectMode = next => { setMode(next); setView('radius'); setExtent('all'); setCursor(candidate.active_center_mm); };
  const stable = data?.stability?.stable;
  const matrix = data?.round_trip;
  const boundRows = data?.boundaries.flatMap(b => Math.abs(b.before.n - b.after.n) > 1e-10 || Math.abs(b.before.inverse_R_per_mm - b.after.inverse_R_per_mm) > 1e-10 ? [{ ...b.before, side: '入射侧' }, { ...b.after, side: '出射侧' }] : [{ ...b.after, side: '截面' }]) || [];
  return <section ref={section} className={`optical-analysis ${expanded ? 'oa-expanded' : ''}`} role={expanded ? 'dialog' : undefined} aria-modal={expanded || undefined} aria-label="光学分析台">
    <header className="oa-header"><div><span className="oa-eyebrow">CAUSTIC & CAVITY ANALYSIS</span><h3>光学分析台 <small>版本 {revisionNumber} · 候选 {candidate.rank}</small></h3></div><button onClick={() => setExpanded(!expanded)}>{expanded ? '收起分析台 · Esc' : '展开分析台 ↗'}</button></header>
    <div className="oa-modes"><button className={mode === 'cavity' ? 'active' : ''} onClick={() => selectMode('cavity')}>激光腔模</button><button className={mode === 'pump' ? 'active' : ''} onClick={() => selectMode('pump')}>泵浦成像</button><span>{data ? `${number(data.wavelength_nm, 1)} nm · ${mode === 'cavity' ? '自洽本征模' : '等效 M² 场景'}` : 'ABCD 物理内核'}</span></div>
    <div className="oa-controls">
      <label>晶体后端面 → M2 / mm<input aria-label="分析 M2 间隙 mm" type="number" min="0.001" max="2000" step="0.1" value={mode === 'pump' ? savedGap : gap} disabled={mode === 'pump'} onChange={e => setGap(e.target.value)} /></label>
      <label>热透镜焦距 / mm<select aria-label="分析热透镜焦距" disabled={mode === 'pump'} value={heat} onChange={e => setHeat(e.target.value)}><option value="">∞ · 冷腔</option>{[2000, 1000, 500, 200, 100, 50].map(f => <option value={f} key={f}>{f}</option>)}</select></label>
      <label>曲线采样<select aria-label="曲线采样密度" value={samples} onChange={e => setSamples(Number(e.target.value))}><option value="300">300 · 快速</option><option value="900">900 · 精细</option><option value="2400">2400 · 高密度</option></select></label>
      <div className="oa-preview"><strong>实时计算预览</strong><small>保存的 M2 间隙 {number(savedGap, 3)} mm</small><button disabled={busy || !data || mode !== 'cavity' || !stable || Math.abs(Number(gap) - savedGap) < 1e-9} onClick={() => onAdoptGap(Number(gap))}>将此间隙用于新设计 →</button></div>
    </div>
    <div className="oa-toolbar"><label>分析量<select aria-label="光学分析量" value={view} onChange={e => setView(e.target.value)}><option value="radius">光束尺寸 w(z)</option><option value="envelope">对称包络 ±w(z)</option><option value="inverse">波前曲率 1/R(z)</option><option value="curvature">波前曲率半径 R(z)</option>{mode === 'cavity' && <option value="stability">M2 稳定性扫描</option>}</select></label>{['radius', 'envelope'].includes(view) && <><select aria-label="光束尺寸单位" value={unit} onChange={e => setUnit(e.target.value)}><option value="um">μm</option><option value="mm">mm</option></select><select aria-label="半径或直径" value={diameter ? 'diameter' : 'radius'} onChange={e => setDiameter(e.target.value === 'diameter')}><option value="radius">半径 w</option><option value="diameter">直径 2w</option></select></>}
      <div className="oa-export"><button disabled={!data} onClick={() => downloadCsv(data, filename, scanning)}>数据 CSV</button><button disabled={!figure} onClick={() => plot.current?.exportImage('svg').catch(err => setError(err.message))}>SVG</button><button disabled={!figure} onClick={() => plot.current?.exportImage('png').catch(err => setError(err.message))}>PNG</button></div>
    </div>
    <div className="oa-workbench"><div className="oa-graph-panel">
      <div className="oa-zoom"><span>视野</span>{!scanning && [['all', '全程'], ['crystal', '晶体'], ['active', '掺杂段'], ['focus', '束腰 ±2 mm']].map(([key, title]) => <button className={extent === key ? 'active' : ''} key={key} onClick={() => setExtent(key)}>{title}</button>)}<button className={pan ? 'active' : ''} onClick={() => setPan(!pan)}>{pan ? '拖动平移' : '框选放大'}</button></div>
      {!scanning && <div className="oa-range"><span>自定 z / mm</span>{[0, 1].map(i => <input type="number" step="any" key={i} aria-label={i ? '视野终点 mm' : '视野起点 mm'} placeholder={number(range[i], 3)} value={customRange[i]} onChange={e => { setCustomRange(prev => prev.map((v, j) => j === i ? e.target.value : v)); setExtent('custom'); }} />)}<small>双击图面复位 · 图例可切换曲线</small></div>}
      {!valid ? <div className="oa-placeholder">请输入 0.001–2000 mm 的 M2 间隙。</div> : error && !data ? <div className="oa-placeholder" role="alert">{error}</div> : !figure ? <div className="oa-placeholder" role="status">正在计算分段 q 参数与稳定性曲线…</div> : <ScientificPlot ref={plot} data={figure.data} layout={figure.layout} filename={filename} onPoint={x => { if (Number.isFinite(x)) { if (scanning) setGap(Number(x.toFixed(6))); else setCursor(x); } }} />}
      <div className="oa-plot-caption">{scanning ? '−1 < m < 1 为稳定区。纵轴初始显示 ±1.5；曲线保留真实数值，可缩放查看。点击曲线即可移动 M2。' : '点击曲线定位游标；输入任意 z 可精确求值。浅色区域为晶体，绿色区域为掺杂段。'}{data && !scanning && ` 实际 ${data.trace.sample_count} 点（包含边界与束腰加密点）。`}</div>
      {data && mode === 'cavity' && !stable && <p className="oa-alert">当前参数下无稳定自洽腔模。{scanning ? '可沿扫描曲线选择稳定区内的 M2 间隙。' : data.cold_reference?.points.length ? '虚线仅为同间隙冷腔参考。' : '不绘制虚构光束；切换稳定性扫描查看边界。'}</p>}
      {error && data && <p role="alert" className="oa-alert">{error}</p>}
    </div><aside className="oa-inspector">
      <div className="oa-inspector-title">精确游标 <span>非插值</span></div><label>z / mm · 相对 M1<input type="number" step="any" aria-label="精确游标 z mm" value={cursor} onChange={e => setCursor(e.target.value)} /></label>
      {point ? <><div className="oa-probe-main"><small>1/e² 强度半径 w</small><strong>{number(point.w_mm * 1000, 6)} <em>μm</em></strong></div><dl><dt>波前半径 R</dt><dd>{number(point.R_mm, 5)} mm</dd><dt>曲率 1/R</dt><dd>{number(point.inverse_R_per_mm, 9)} mm⁻¹</dd><dt>Re(q)</dt><dd>{number(point.q_real_mm, 6)} mm</dd><dt>Im(q)</dt><dd>{number(point.q_imag_mm, 6)} mm</dd><dt>介质折射率 n</dt><dd>{number(point.n, 7)}</dd></dl></> : <p className="oa-note">{data && cursor !== '' && (Number(cursor) < data.z_range_mm[0] || Number(cursor) > data.z_range_mm[1]) ? `可用范围 ${number(data.z_range_mm[0], 3)} 至 ${number(data.z_range_mm[1], 3)} mm` : data?.trace.points.length ? '正在求值…' : '无可用腔模读数'}</p>}
      <p className="oa-note">介质 / 透镜边界取出射侧，终点取内侧。R = ∞ 表示平波前。</p>
      {matrix && <div className="oa-matrix"><div className="oa-inspector-title">往返矩阵 · M1</div><div className="oa-matrix-grid">{[['A', matrix.A, ''], ['B', matrix.B_mm, 'mm'], ['C', matrix.C_per_mm, 'mm⁻¹'], ['D', matrix.D, '']].map(([key, val, suffix]) => <div key={key}><small>{key} {suffix}</small><strong>{number(val, 7)}</strong></div>)}</div><dl><dt>det(M)</dt><dd>{number(matrix.determinant, 9)}</dd><dt>m = (A+D)/2</dt><dd className={stable ? 'oa-good' : 'oa-bad'}>{number(data.stability.m, 8)}</dd><dt>稳定余量 1−|m|</dt><dd>{number(1 - Math.abs(data.stability.m), 7)}</dd></dl></div>}
      <p className="oa-note">{data?.planes}</p>
    </aside></div>
    {data && <div className="oa-details"><div className="oa-detail-tabs">{[['points', '束腰与关键截面'], ['raw', '原始数值'], ['model', '模型与假设']].map(([key, name]) => <button className={detail === key ? 'active' : ''} onClick={() => setDetail(key)} key={key}>{name}</button>)}</div>
      {detail === 'points' && <><div className="oa-waists">{data.trace.waists.length ? data.trace.waists.map((w, i) => <article key={i}><small>解析束腰 {i + 1} · z {number(w.z_mm, 6)} mm</small><strong>w₀ {number(w.w_mm * 1000, 6)} μm</strong><span>局部 zR {number(w.z_R_mm, 6)} mm · 远场半角 {number(w.divergence_half_mrad, 5)} mrad</span></article>) : <p className="oa-note">当前范围内没有可报告的解析束腰。</p>}</div><div className="oa-table"><table><thead><tr><th>截面 / mm</th><th>取值侧</th><th>n</th><th>w / μm</th><th>R / mm</th></tr></thead><tbody>{boundRows.map((p, i) => <tr key={i}><td>{data.markers.filter(m => Math.abs(m.z_mm - p.z_mm) < 1e-7).map(m => m.label).join(' / ') || '截面'} · {number(p.z_mm, 6)}</td><td>{p.side}</td><td>{number(p.n, 6)}</td><td>{number(p.w_mm * 1000, 6)}</td><td>{number(p.R_mm, 5)}</td></tr>)}</tbody></table></div></>}
      {detail === 'raw' && <><div className="oa-pagination"><span>{data.trace.sample_count} 个传播采样点 · 保留内部精度，显示 8 位小数</span><button disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1} / {Math.max(1, Math.ceil(data.trace.points.length / 50))}</span><button disabled={(page + 1) * 50 >= data.trace.points.length} onClick={() => setPage(page + 1)}>下一页</button></div><div className="oa-table oa-raw"><table><thead><tr><th>z / mm</th><th>w / μm</th><th>R / mm</th><th>Re(q) / mm</th><th>Im(q) / mm</th><th>n</th></tr></thead><tbody>{data.trace.points.slice(page * 50, (page + 1) * 50).map((p, i) => <tr key={i}>{[p.z_mm, p.w_mm * 1000, p.R_mm, p.q_real_mm, p.q_imag_mm, p.n].map((v, j) => <td key={j}>{number(v, 8)}</td>)}</tr>)}</tbody></table></div></>}
      {detail === 'model' && <div className="oa-model"><p>真空波长 {number(data.wavelength_nm, 2)} nm；q 定义：1/q = 1/R − iλ₀/(πnw²)。z 为物理坐标，所有透镜均为薄透镜模型。显示的小数位反映数值精度，不代表器件测量精度。</p>{data.notes.map((note, i) => <p key={i}>{note}</p>)}{mode === 'pump' && <p>等效 M² = {number(data.estimated_M2, 6)}；用于芯径 / NA 假设场景的二阶矩近似，不能据此确认实际光纤模场。</p>}{data.scan && <p>冷腔稳定间隙上界 d₂ &lt; {number(data.scan.cold_upper_exclusive_mm, 8)} mm。热透镜曲线为独立焦距场景，未从 6 W 泵浦推定实际焦距。</p>}<p>当前预览直接调用 ABCD 内核，不调用 LLM；不会修改已保存的设计坐标。采用新间隙后由 Agent 生成完整新版本。</p></div>}
    </div>}
  </section>;
}
