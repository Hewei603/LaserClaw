import React, { useMemo, useRef, useState } from 'react';
import ScientificPlot from './ScientificPlot';
import './OpticalFieldView.css';

const fmt = (value, digits = 3) => Number.isFinite(value) ? Number(value.toFixed(digits)).toLocaleString('zh-CN', { maximumFractionDigits: digits }) : '—';
const segmentKind = (element) => {
  if (!(element.n > 1) || !(element.length_mm > 0)) return 'air';
  if (/端帽|无掺杂|undoped|cap/i.test(element.name)) return 'cap';
  if (/掺杂|增益|doped|active|Nd[:：]/i.test(element.name)) return 'active';
  return 'medium';
};

export function systemSegments(system) {
  let z = 0;
  return (system?.elements || []).map((element, index) => {
    const start = z;
    z += Number(element.length_mm) || 0;
    return { ...element, index, start, end: z, region: segmentKind(element) };
  });
}

export default function OpticalFieldView({ analysis, system = analysis?.system, revisionLabel = '' }) {
  const [unit, setUnit] = useState('um'), [diameter, setDiameter] = useState(false);
  const [envelope, setEnvelope] = useState(false), [extent, setExtent] = useState('all');
  const [error, setError] = useState('');
  const [showSpot, setShowSpot] = useState(false), [spotIndex, setSpotIndex] = useState(null);
  const plot = useRef(null), spotPlot = useRef(null);
  const segments = useMemo(() => systemSegments(system), [system]);
  const medium = segments.filter(segment => segment.region !== 'air');
  const active = medium.filter(segment => segment.region === 'active');
  const first = segments[0]?.start || 0, last = segments.at(-1)?.end || 0;
  const start = medium[0]?.start, end = medium.at(-1)?.end;
  const planes = analysis?.planes || {};
  const t = planes.tangential, s = planes.sagittal;
  const stable = analysis?.stable_both_planes;
  const cavity = system?.mode !== 'single_pass';
  const same = t?.samples?.length > 0 && t.samples.length === s?.samples?.length
    && t.samples.every((point, index) => Math.abs(point.z_mm - s.samples[index].z_mm) < 1e-8
      && Math.abs(point.radius_mm - s.samples[index].radius_mm) < 1e-10);
  const factor = (unit === 'um' ? 1000 : 1) * (diameter ? 2 : 1);
  const widthLabel = diameter ? '直径 2w' : '半径 w';
  const suffix = unit === 'um' ? 'μm' : 'mm';
  const waist = Object.entries(planes).flatMap(([plane, data]) => (data.waists || []).map(item => ({ ...item, plane })))
    .sort((a, b) => a.radius_mm - b.radius_mm)[0];
  const profiles = same ? [['tangential', t]] : Object.entries(planes);
  const curves = profiles.flatMap(([plane, data], index) => {
    const name = same ? 'T=S' : plane === 'tangential' ? '切向 T' : '弧矢 S';
    const curve = {
      type: 'scatter', mode: 'lines', name: system?.wavelength_nm + ' nm · ' + name,
      x: data.samples?.map(point => point.z_mm) || [],
      y: data.samples?.map(point => point.radius_mm * factor) || [],
      line: { color: index ? '#f6bf72' : '#70dfcc', width: 2.5, dash: index ? 'dash' : 'solid' },
      hovertemplate: 'z = %{x:.4f} mm<br>' + widthLabel + ' = %{y:.3f} ' + suffix + '<extra>%{fullData.name}</extra>',
    };
    return envelope ? [curve, { ...curve, y: curve.y.map(value => -value), showlegend: false, hoverinfo: 'skip' }] : [curve];
  });
  const markerRadius = waist?.radius_mm * factor;
  if (waist) curves.push({ type: 'scatter', mode: 'markers', name: '解析束腰',
    x: [waist.z_mm], y: [markerRadius], marker: { color: '#f6bf72', size: 9, symbol: 'diamond' },
    hovertemplate: '解析束腰 z = %{x:.4f} mm<br>' + widthLabel + ' = %{y:.3f} ' + suffix + '<extra></extra>' });
  const viewRange = extent === 'active' && active.length ? [active[0].start, active.at(-1).end]
    : extent === 'medium' && medium.length ? [start, end] : [first, last];
  const padding = Math.max(.15, (viewRange[1] - viewRange[0]) * .025);
  const shapes = medium.map(segment => ({
    type: 'rect', xref: 'x', yref: 'paper', x0: segment.start, x1: segment.end, y0: 0, y1: 1,
    fillcolor: segment.region === 'active' ? '#62c5a224' : '#b2c2d019', line: { width: 0 }, layer: 'below',
  }));
  const marks = [...segments.filter(segment => segment.kind !== 'space' && segment.kind !== 'grin'),
    ...medium.filter((segment, index) => index === 0 || Math.abs(segment.start - medium[index - 1].end) > 1e-8)];
  const regions = medium.reduce((groups, segment) => {
    const previous = groups.at(-1);
    if (previous?.region === segment.region && Math.abs(previous.end - segment.start) < 1e-8) previous.end = segment.end;
    else groups.push({ ...segment });
    return groups;
  }, []);
  const layout = {
    title: { text: system?.wavelength_nm + ' nm · ' + widthLabel + '(z)' + (revisionLabel ? ' · ' + revisionLabel : ''), x: .04, font: { size: 14 } },
    height: 430, autosize: true, margin: { l: 76, r: 25, t: 65, b: 90 },
    paper_bgcolor: '#111c28', plot_bgcolor: '#111c28',
    font: { color: '#d6e2ef', size: 12 }, hovermode: 'x unified', shapes: [...shapes,
      ...marks.map(segment => ({ type: 'line', xref: 'x', yref: 'paper', x0: segment.start, x1: segment.start,
        y0: 0, y1: 1, line: { color: '#cbd5e145', width: 1, dash: 'dot' }, layer: 'below' }))],
    xaxis: { title: { text: '沿光路物理位置 z / mm · 起点为首个元件', standoff: 15 },
      range: [viewRange[0] - padding, viewRange[1] + padding], gridcolor: '#ffffff12', zeroline: false },
    yaxis: { title: { text: widthLabel + ' / ' + suffix + ' · 1/e² 强度', standoff: 12 },
      gridcolor: '#ffffff12', zerolinecolor: '#ffffff35', rangemode: 'normal' },
    annotations: regions.map(region => ({ x: (region.start + region.end) / 2, y: 1.025, xref: 'x', yref: 'paper',
      text: region.region === 'active' ? '掺杂 / 增益段' : region.region === 'cap' ? '无掺杂端帽' : '介质',
      showarrow: false, font: { size: 11, color: '#bcd3d8' } })),
    legend: { orientation: 'h', x: 0, y: -.23, font: { size: 12 } },
    uirevision: revisionLabel + ':' + unit + ':' + diameter + ':' + envelope + ':' + extent,
  };
  const exportCSV = () => {
    const rows = [['平面', 'z_mm', diameter ? 'diameter_' + unit : 'radius_' + unit, 'n'],
      ...Object.entries(planes).flatMap(([plane, data]) => (data.samples || []).map(point =>
        [plane, point.z_mm, point.radius_mm * factor, point.n]))];
    const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'optical-field-' + revisionLabel + '.csv'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const x = z => 40 + (z - first) / Math.max(last - first, .001) * 820;
  const sections = (t?.elements || []).flatMap((point, index) => {
    const other = s?.elements?.[index];
    return other && Math.abs(other.z_mm - point.z_mm) < 1e-8
      && point.radius_mm > 0 && other.radius_mm > 0 ? [{ point, other, index }] : [];
  });
  const target = active.length ? (active[0].start + active.at(-1).end) / 2 : (first + last) / 2;
  const representative = [...sections].sort((a, b) => Math.abs(a.point.z_mm - target) - Math.abs(b.point.z_mm - target))[0];
  const section = sections.find(item => item.index === spotIndex) || representative;
  const spot = useMemo(() => {
    if (!section || !showSpot) return null;
    const coordinateFactor = unit === 'um' ? 1000 : 1;
    const wt = section.point.radius_mm * coordinateFactor, ws = section.other.radius_mm * coordinateFactor;
    const range = Math.max(wt, ws) * 2.2;
    const coordinates = Array.from({ length: 129 }, (_, index) => (index / 128 * 2 - 1) * range);
    return { wt, ws, range, data: [{ type: 'heatmap', x: coordinates, y: coordinates,
      z: coordinates.map(y => coordinates.map(xValue => Math.exp(-2 * ((xValue / wt) ** 2 + (y / ws) ** 2)))),
      zmin: 0, zmax: 1, zsmooth: 'best', colorscale: [[0, '#111c28'], [.08, '#203c70'], [.3, '#7056a6'], [.6, '#dd8a64'], [1, '#fff1b3']],
      colorbar: { title: { text: 'I / I₀' }, thickness: 12, tickvals: [0, .1353, .5, 1] },
      hovertemplate: '切向 x = %{x:.3f} ' + suffix + '<br>弧矢 y = %{y:.3f} ' + suffix + '<br>相对光强 %{z:.4f}<extra></extra>' }] };
  }, [section?.point, section?.other, showSpot, unit, suffix]);
  if (!analysis || !system) return null;
  return <section className="field-view" aria-label="光路位置与光场半径">
    <div className="field-heading"><div><span className="wb-eyebrow">光路与模场</span><h3>{system.wavelength_nm} nm {cavity ? '腔内基模' : '单程光束'} · 光斑随位置的变化</h3></div>
      <span className={'field-state ' + (stable === false ? 'is-unstable' : '')}>{cavity ? stable ? '几何稳定' : '无稳定基模' : '单程传播'}{revisionLabel && ' · ' + revisionLabel}</span></div>
    <div className="field-metrics">
      <div><small>{cavity ? '首末元件间距' : '传播总长'}</small><strong>{fmt(last - first)} <em>mm</em></strong></div>
      {!!medium.length && <><div><small>首元件 → 首段介质</small><strong>{fmt(start - first)} <em>mm</em></strong></div>
        <div><small>介质物理总长</small><strong>{fmt(medium.reduce((sum, segment) => sum + segment.end - segment.start, 0))} <em>mm</em></strong></div>
        <div><small>介质 → 末元件</small><strong>{fmt(last - end)} <em>mm</em></strong></div></>}
      {!!active.length && <div><small>掺杂 / 增益段总长</small><strong>{fmt(active.reduce((sum, segment) => sum + segment.end - segment.start, 0))} <em>mm</em></strong></div>}
      {waist && <div><small>最小解析束腰 · {same ? 'T=S' : waist.plane === 'tangential' ? 'T' : 'S'} 半径</small><strong>{fmt(waist.radius_mm * 1000, 2)} <em>μm</em></strong></div>}
    </div>
    <div className="field-layout">
      <svg viewBox="0 0 900 106" role="img" aria-label="按物理位置缩放的光路示意；纵向尺寸不按比例">
        <line x1="40" x2="860" y1="40" y2="40" stroke="#8196ab" strokeWidth="1" strokeDasharray="5 5" />
        {medium.map(segment => <g key={segment.index}><rect x={x(segment.start)} y="22" width={Math.max(1, x(segment.end) - x(segment.start))} height="36"
          fill={segment.region === 'active' ? '#286b58' : '#394b5f'} stroke={segment.region === 'active' ? '#7de3bd' : '#a7b8ca'} rx="2"><title>{segment.name + '：' + fmt(segment.start) + '–' + fmt(segment.end) + ' mm'}</title></rect>
          <text x={x((segment.start + segment.end) / 2)} y="16" textAnchor="middle" fill="#cbd9e6" fontSize="11">{fmt(segment.end - segment.start)} mm</text></g>)}
        {segments.filter(segment => segment.kind !== 'space' && segment.kind !== 'grin').map((segment, index) => <g key={segment.index}>
          {segment.kind === 'mirror' ? <path d={segment.radius_mm == null ? 'M ' + x(segment.start) + ' 13 V 66'
            : 'M ' + x(segment.start) + ' 13 Q ' + (x(segment.start) + (index === 0 ? -12 : 12)) + ' 40 ' + x(segment.start) + ' 66'}
            fill="none" stroke="#e1eaf4" strokeWidth="3" />
            : <line x1={x(segment.start)} x2={x(segment.start)} y1="13" y2="66" stroke="#d8afef" strokeWidth="3" />}
          <text x={x(segment.start)} y={index % 2 ? 94 : 78} textAnchor={segment.index === 0 ? 'start' : segment.index === segments.length - 1 ? 'end' : 'middle'} fill="#deebf6" fontSize="11">{segment.name.length > 15 ? segment.name.slice(0, 15) + '…' : segment.name}</text>
        </g>)}
      </svg>
      <div className="field-region-key"><span className="active-region">掺杂 / 增益段</span><span>端帽 / 其他介质</span><small>轴向位置按比例；示意图不表示实际光斑粗细。</small></div>
    </div>
    <div className="field-toolbar">
      <label>显示<select aria-label="模场曲线显示方式" value={envelope ? 'envelope' : 'radius'} onChange={event => setEnvelope(event.target.value === 'envelope')}>
        <option value="radius">光斑尺寸 w(z)</option><option value="envelope">对称包络 ±w(z)</option></select></label>
      <label>单位<select aria-label="模场曲线单位" value={unit} onChange={event => setUnit(event.target.value)}><option value="um">μm</option><option value="mm">mm</option></select></label>
      <label>尺寸<select aria-label="模场半径或直径" value={diameter ? 'diameter' : 'radius'} onChange={event => setDiameter(event.target.value === 'diameter')}><option value="radius">半径 w</option><option value="diameter">直径 2w</option></select></label>
      <label>视野<select aria-label="模场显示范围" value={extent} onChange={event => setExtent(event.target.value)}><option value="all">全光路</option>{!!medium.length && <option value="medium">介质区域</option>}{!!active.length && <option value="active">掺杂段</option>}</select></label>
      <div className="field-export"><button onClick={exportCSV}>CSV</button><button onClick={() => plot.current?.exportImage('svg').catch(e => setError(e.message))}>SVG</button><button onClick={() => plot.current?.exportImage('png').catch(e => setError(e.message))}>PNG</button></div>
    </div>
    {error && <p role="alert" className="wb-error">{error}</p>}
    {curves.some(curve => curve.x?.length) ? <ScientificPlot ref={plot} data={curves} layout={layout} filename={'optical-field-' + revisionLabel} />
      : <p className="field-empty">当前几何没有稳定腔模，保留元件位置，不绘制虚构光场。请调整参数后复算。</p>}
    <p className="field-caption">半径 w 取光强降至中心 1/e²（约13.5%）的位置；直径为2w。尺寸图纵轴自动缩放以查看细节；对称包络以光轴为中心。{same ? 'T=S 表示同一光束的两个截面重合。' : 'T/S 是同一光束的切向与弧矢截面。'}它们不是808 nm与1064 nm两束光。</p>
    {cavity && <p className="field-note">本图是{system.wavelength_nm} nm计算基模。未提供独立泵浦模型时不叠画808 nm光斑；这张图不能证明实际泵浦已匹配，也不预测输出功率或效率。</p>}
    {!!sections.length && <details className="field-spot" onToggle={event => { if (event.currentTarget === event.target) setShowSpot(event.currentTarget.open); }}>
      <summary>查看截面光斑 · 理想基模强度分布</summary>
      {showSpot && <><div className="field-toolbar"><label>计算截面<select aria-label="光斑截面位置" value={section.index} onChange={event => setSpotIndex(Number(event.target.value))}>{sections.map(item =>
        <option key={item.index} value={item.index}>{item.point.name} · z={fmt(item.point.z_mm, 4)} mm</option>)}</select></label>
        <button onClick={() => spotPlot.current?.exportImage('png').catch(e => setError(e.message))}>导出光斑 PNG</button></div>
        {spot && <ScientificPlot ref={spotPlot} data={spot.data} layout={{
          title: { text: '理想 ' + system.wavelength_nm + ' nm 基模 · z=' + fmt(section.point.z_mm, 4) + ' mm · wT=' + fmt(section.point.radius_mm * 1000, 2) + ' μm · wS=' + fmt(section.other.radius_mm * 1000, 2) + ' μm', x: .04, font: { size: 13 } },
          height: 390, autosize: true, paper_bgcolor: '#111c28', plot_bgcolor: '#111c28',
          margin: { l: 72, r: 85, t: 50, b: 60 }, font: { color: '#d6e2ef', size: 12 },
          xaxis: { title: { text: '切向 x / ' + suffix }, range: [-spot.range, spot.range], constrain: 'domain', zeroline: false },
          yaxis: { title: { text: '弧矢 y / ' + suffix }, range: [-spot.range, spot.range], scaleanchor: 'x', scaleratio: 1, zeroline: false },
          shapes: [{ type: 'circle', x0: -spot.wt, x1: spot.wt, y0: -spot.ws, y1: spot.ws, line: { color: '#a5f1d5', width: 1.5, dash: 'dot' } }],
        }} filename={'beam-spot-' + revisionLabel + '-z' + fmt(section.point.z_mm)} />}
        <p className="field-caption">z={fmt(section.point.z_mm, 4)} mm；切向半径 {fmt(section.point.radius_mm * 1000, 2)} μm，弧矢半径 {fmt(section.other.radius_mm * 1000, 2)} μm。虚线为1/e²强度边界。图由计算半径生成高斯基模分布，非实拍光斑；图中心仅代表模型腔轴。</p>
      </>}
    </details>}
    <details className="field-positions"><summary>逐段位置与参数 · {segments.length} 个元件</summary><div className="wb-table-wrap"><table><thead><tr><th>元件 / 传播段</th><th>起点 z / mm</th><th>终点 z / mm</th><th>参数</th></tr></thead><tbody>{segments.map(segment => <tr key={segment.index}>
      <td>{segment.name}</td><td>{fmt(segment.start, 4)}</td><td>{fmt(segment.end, 4)}</td><td>{segment.kind === 'mirror' ? segment.radius_mm == null ? '平面镜' : 'R = ' + fmt(segment.radius_mm) + ' mm'
        : segment.kind === 'lens' ? '空气等效 f = ' + fmt(segment.focal_mm) + ' mm' : '长度 ' + fmt(segment.length_mm) + ' mm · n = ' + fmt(segment.n, 6)}</td>
    </tr>)}</tbody></table></div></details>
  </section>;
}
