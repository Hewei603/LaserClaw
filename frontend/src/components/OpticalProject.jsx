import React, { useEffect, useMemo, useRef, useState } from 'react';
import { workbenchApi } from '../api/workbench';
import ScientificPlot from './ScientificPlot';
import OpticalFieldView from './OpticalFieldView';
import OpticalScanView from './OpticalScanView';
import './OpticalProject.css';

const kinds = { space: '传播段 / 晶体', lens: '薄透镜', mirror: '腔镜', thick_lens: '厚透镜 / 曲面基底', grin: 'GRIN', matrix: '自定义 ABCD' };
const fields = { space: ['length_mm', 'n'], lens: ['focal_mm'], mirror: ['radius_mm', 'aoi_deg'], thick_lens: ['length_mm', 'n', 'front_radius_mm', 'back_radius_mm'], grin: ['length_mm', 'n', 'gradient_per_mm'], matrix: [] };
const labels = { length_mm: '长度 / mm', n: '折射率 n', focal_mm: '空气等效焦距 f / mm', radius_mm: '曲率 R / mm', aoi_deg: '入射角 / °', front_radius_mm: '前面 R / mm', back_radius_mm: '后面 R / mm', gradient_per_mm: 'GRIN g / mm⁻¹' };
const layout = (x, y) => ({ height: 350, autosize: true, margin: { l: 68, r: 25, t: 35, b: 65 }, paper_bgcolor: '#131d2a', plot_bgcolor: '#131d2a', font: { color: '#becbda', size: 11 }, xaxis: { title: { text: x }, gridcolor: '#ffffff10' }, yaxis: { title: { text: y }, gridcolor: '#ffffff10' }, legend: { orientation: 'h', y: 1.15 }, hovermode: 'x unified' });
const download = (name, data) => { const u = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); const a = document.createElement('a'); a.href = u; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(u), 1000); };
const initial = { title: '新光学工程', system: { mode: 'single_pass', wavelength_nm: 1064, input_radius_mm: 0.3, input_curvature_mm: null, beam_quality_m2: 1, samples_per_segment: 100, elements: [{ uid: crypto.randomUUID(), name: '自由传播', kind: 'space', length_mm: 100, n: 1 }] }, parts: [], assumptions: [], notes: '' };

export default function OpticalProject({ caseId, onAsk, pending = false }) {
  const [state, setState] = useState(null), [draft, setDraft] = useState(null), [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [unlock, setUnlock] = useState(false), [newKind, setNewKind] = useState('space');
  const [map, setMap] = useState(null), [plotType, setPlotType] = useState('radius'), [raw, setRaw] = useState('');
  const [x, setX] = useState({ element_index: 1, parameter: 'length_mm', start: 1, stop: 20, count: 41 });
  const [y, setY] = useState({ element_index: 5, parameter: 'length_mm', start: 1, stop: 100, count: 61 });
  const plot = useRef(null);
  const accept = data => {
    const project = data.current?.project || initial;
    setState(data); setDraft(structuredClone(project)); setDirty(false); setUnlock(false); setMap(data.scan || null); setRaw('');
    if (data.scan) { setX(data.scan.x_axis); setY(data.scan.y_axis); }
    else {
      const spaces = project.system.elements.flatMap((e, i) => e.kind === 'space' ? [i] : []);
      if (spaces.length) { setX({ element_index: spaces[0], parameter: 'length_mm', start: 1, stop: 20, count: 41 }); setY({ element_index: spaces.at(-1), parameter: 'length_mm', start: 1, stop: 200, count: 81 }); }
    }
  };
  useEffect(() => { let alive = true; workbenchApi.getProject(caseId).then(d => { if (alive) accept(d); }).catch(e => { if (alive) setError(e.message); }); return () => { alive = false; }; }, [caseId]);
  const edit = next => { setDraft(next); setDirty(true); setNotice(''); setMap(null); };
  const applyRaw = () => {
    try {
      const next = JSON.parse(raw || JSON.stringify(draft));
      if (!next || typeof next.title !== 'string' || !Array.isArray(next.system?.elements) || !next.system.elements.length || !Array.isArray(next.parts) || !Array.isArray(next.assumptions)
        || next.system.elements.some(e => !e || !fields[e.kind] || typeof e.name !== 'string')
        || next.parts.some(p => !p || !Number.isInteger(p.element_index) || !Array.isArray(p.locked_parameters) || !Array.isArray(p.unknowns))) throw new Error();
      edit(next); setRaw(''); setError('');
    } catch { setError('工程 JSON 格式或结构不正确：需要 title、system.elements、parts 和 assumptions；数值参数将在保存时校验。'); }
  };
  const changeSystem = (key, value) => edit({ ...draft, system: { ...draft.system, [key]: value } });
  const changeElement = (index, key, value) => edit({ ...draft, system: { ...draft.system, elements: draft.system.elements.map((e, i) => i === index ? { ...e, [key]: value } : e) } });
  const current = state?.current;
  const analysis = current?.analysis;
  const savedElements = current?.project.system.elements || [];
  const profile = useMemo(() => Object.entries(analysis?.planes || {}).map(([, data], i) => ({ type: 'scatter', mode: 'lines', name: i ? '弧矢 S' : '切向 T', x: data.samples.map(p => p.z_mm), y: data.samples.map(p => plotType === 'radius' ? p.radius_mm * 1000 : p.curvature_mm), line: { color: i ? '#e8b879' : '#80d6c5', dash: i ? 'dash' : 'solid' } })), [analysis, plotType]);
  const save = async () => { setBusy(true); setError(''); try { await workbenchApi.saveProject(caseId, { base_revision_id: state?.revisions[0]?.id ?? null, project: draft, change_note: current && current.revision_id !== state.revisions[0]?.id ? `从历史版本 #${current.revision_id} 恢复并复算` : '用户修改光学工程并复算', unlock_quote: unlock ? '用户在工程编辑器明确解锁' : '' }); accept(await workbenchApi.getProject(caseId)); setNotice('新版本已保存并完成计算。'); } catch (e) { setError(e.message); } finally { setBusy(false); } };
  const loadRevision = async id => { setBusy(true); setError(''); setNotice(''); try { accept(await workbenchApi.getProject(caseId, id)); } catch (err) { setError(err.message); } finally { setBusy(false); } };
  const scan = async () => { setBusy(true); setError(''); try { setMap(await workbenchApi.scanProject(caseId, current.revision_id, { system: current.project.system, x, y })); } catch (e) { setError(e.message); } finally { setBusy(false); } };
  const axisEditor = (axis, setAxis, name) => <fieldset><legend>{name} 扫描轴</legend><select aria-label={`${name} 元件`} value={axis.element_index} onChange={e => { const i = Number(e.target.value); setAxis({ ...axis, element_index: i, parameter: fields[savedElements[i].kind][0] }); }}>{savedElements.map((e, i) => fields[e.kind].length > 0 && <option value={i} key={i}>{e.name}</option>)}</select><select aria-label={`${name} 参数`} value={axis.parameter} onChange={e => setAxis({ ...axis, parameter: e.target.value })}>{(fields[savedElements[axis.element_index]?.kind] || []).map(p => <option key={p} value={p}>{labels[p]}</option>)}</select>{[['start', '起点'], ['stop', '终点'], ['count', '采样数']].map(([key, label]) => <label key={key}>{label}<input aria-label={`${name} ${label}`} type="number" value={axis[key]} onChange={e => setAxis({ ...axis, [key]: Number(e.target.value) })} /></label>)}</fieldset>;
  if (!draft) return <p>读取光学工程…</p>;
  return <section className="op-workspace">
    <div className="wb-row"><div><span className="wb-eyebrow">OPTICAL ENGINEERING</span><h3>光学工程 · 可编辑与复算</h3></div><select aria-label="工程版本" disabled={busy} value={current?.revision_id || ''} onChange={e => loadRevision(Number(e.target.value))}><option value="" disabled>尚未保存</option>{state?.revisions.map(r => <option value={r.id} key={r.id}>版本 #{r.id} · {r.change_note}</option>)}</select></div>
    {!current && <p className="wb-muted">Agent 可从已有设计创建工程，也可在这里添加元件开始。<button className="btn btn-secondary" onClick={() => onAsk('请读取最新已存光路设计，将采用的候选导入可编辑光学工程，保留已有元件、角色与参数约束。')}>让 Agent 创建工程</button></p>}
    {error && <p role="alert" className="wb-error">{error}</p>}{notice && <p role="status" className="op-notice">{notice}</p>}
    {pending && <p className="field-note">Agent 正在生成新方案。以下显示已保存工程，新的计算结果尚未自动取代这一版本。</p>}
    {analysis && <OpticalFieldView analysis={analysis} system={current.project.system} revisionLabel={"工程 #" + current.revision_id} />}
    {current && <details className="op-evidence"><summary>方案假设与待核验项 · {current.project.assumptions.length} 项假设</summary>
      <p>{current.project.notes}</p>{current.project.assumptions.map((item, index) => <p key={index}>{item}</p>)}
      {current.project.parts.filter(part => part.unknowns.length).map(part => <div key={part.element_index}><strong>{savedElements[part.element_index]?.name}</strong><ul>{part.unknowns.map((item, index) => <li key={index}>{item}</li>)}</ul></div>)}
    </details>}
    <details className="op-settings" open={!current || undefined}><summary>编辑工程参数与已有元件约束</summary>
    <div className="op-controls"><label>工程标题<input aria-label="工程标题" value={draft.title} onChange={e => edit({ ...draft, title: e.target.value })} /></label><label>系统类型<select value={draft.system.mode} onChange={e => changeSystem('mode', e.target.value)}><option value="standing_wave">驻波腔</option><option value="ring">共面环形腔</option><option value="single_pass">单程传播</option></select></label><label>波长 / nm<input type="number" value={draft.system.wavelength_nm} onChange={e => changeSystem('wavelength_nm', Number(e.target.value))} /></label>{draft.system.mode === 'single_pass' && <><label>输入半径 / mm<input type="number" value={draft.system.input_radius_mm ?? ''} onChange={e => changeSystem('input_radius_mm', Number(e.target.value))} /></label><label>输入波前 R / mm<input type="number" placeholder="空白 = 束腰" value={draft.system.input_curvature_mm ?? ''} onChange={e => changeSystem('input_curvature_mm', e.target.value === '' ? null : Number(e.target.value))} /></label><label>等效 M²<input type="number" min="1" value={draft.system.beam_quality_m2 || 1} onChange={e => changeSystem('beam_quality_m2', Number(e.target.value))} /></label></>}</div>
    <details className="op-editor" open={!current || undefined}><summary>元件参数 · {draft.system.elements.length} 个元件（展开编辑）</summary>
    <label className="op-unlock"><input type="checkbox" checked={unlock} onChange={e => setUnlock(e.target.checked)} />本次明确解锁已有元件参数（历史版本保留）</label>
    <div className="op-elements">{draft.system.elements.map((e, i) => { const part = draft.parts.find(p => p.element_index === i); const locked = key => !unlock && part?.locked_parameters.includes(key); return <article key={e.uid || i}><div className="wb-row"><strong>{i + 1}. {e.name}</strong><small>{kinds[e.kind]} {part?.ownership === 'owned' ? '· 已有实物' : ''} {part?.locked_parameters.length ? '· 已锁定' : ''}</small></div><label>元件名称<input aria-label={`元件 ${i + 1} 名称`} value={e.name} onChange={event => changeElement(i, 'name', event.target.value)} /></label><div className="op-controls">{fields[e.kind].map(key => <label key={key}>{labels[key]}<input aria-label={`${e.name} ${labels[key]}`} type="number" step="any" disabled={locked(key)} value={e[key] ?? ''} placeholder={key.includes('radius') ? '空白 = 平面' : ''} onChange={event => changeElement(i, key, event.target.value === '' ? null : Number(event.target.value))} /></label>)}</div>{e.kind === 'matrix' && <p>矩阵在下方完整模型中填写 matrix_t / matrix_s：[A, B, C, D]，采用 (y, nθ) 坐标。</p>}{part && <details><summary>元件依据与未知项</summary><p>{part.source}</p>{part.unknowns.map((u, j) => <p key={j}>{u}</p>)}</details>}<button disabled={!!part?.locked_parameters.length && !unlock} onClick={() => edit({ ...draft, system: { ...draft.system, elements: draft.system.elements.filter((_, j) => j !== i) }, parts: draft.parts.filter(p => p.element_index !== i).map(p => ({ ...p, element_index: p.element_index > i ? p.element_index - 1 : p.element_index })) })}>移除元件</button></article>; })}</div>
    <div className="wb-row op-actions"><select aria-label="新增元件类型" value={newKind} onChange={e => setNewKind(e.target.value)}>{Object.entries(kinds).map(([key, label]) => <option value={key} key={key}>{label}</option>)}</select><button className="btn btn-secondary" onClick={() => { const index = draft.system.mode === 'standing_wave' ? draft.system.elements.length - 1 : draft.system.elements.length; const e = { uid: crypto.randomUUID(), name: `${kinds[newKind]} ${draft.system.elements.length + 1}`, kind: newKind, ...(newKind === 'space' ? { length_mm: 10, n: 1 } : newKind === 'lens' ? { focal_mm: 100 } : newKind === 'mirror' ? { radius_mm: null } : newKind === 'matrix' ? { matrix_t: [1, 0, 0, 1] } : { length_mm: 5, n: 1.5, front_radius_mm: null, back_radius_mm: null }) }; const elems = [...draft.system.elements]; elems.splice(index, 0, e); edit({ ...draft, system: { ...draft.system, elements: elems }, parts: draft.parts.map(p => ({ ...p, element_index: p.element_index >= index ? p.element_index + 1 : p.element_index })) }); }}>添加元件</button><button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? '计算中…' : '保存新版本并复算'}</button></div>
    </details>
    <p className="wb-engine">{dirty ? '有未保存修改；下方图表仍对应已保存版本。' : `图表对应已保存版本 ${current ? `#${current.revision_id}` : '—'}`} 曲面透射的 R 正号指曲率中心沿传播方向；反射镜正 R 指凹面。</p>
    <details className="op-raw"><summary>完整工程模型 / 参数来源 / 假设</summary><p>{draft.notes}</p>{draft.assumptions.map((a, i) => <p key={i}>{a}</p>)}<textarea aria-label="工程 JSON" rows={12} value={raw || JSON.stringify(draft, null, 2)} onChange={e => setRaw(e.target.value)} /><button className="btn btn-secondary" onClick={applyRaw}>应用模型编辑</button></details>
    </details>
    {analysis && <><div className="wb-row"><h3>{analysis.stable_both_planes === undefined ? '单程传播' : analysis.stable_both_planes ? 'T / S 双平面稳定' : '存在失稳或临界平面'}</h3><button className="btn btn-secondary" onClick={() => download(`optical-project-${current.revision_id}.json`, current)}>导出完整工程</button></div>
      <details className="op-wavefront"><summary>高级分析 · 波前曲率与精确截面数据</summary>
      <div className="wb-row"><select aria-label="工程图表类型" value={plotType} onChange={e => setPlotType(e.target.value)}><option value="radius">光束半径</option><option value="curvature">波前曲率</option></select><button className="btn btn-secondary" onClick={() => plot.current?.exportImage('svg').catch(e => setError(e.message))}>导出工程 SVG</button></div>
      <ScientificPlot ref={plot} data={profile} layout={layout('物理位置 z / mm', plotType === 'radius' ? '1/e² 半径 w / μm' : '波前 R / mm')} filename={`project-${current.revision_id}`} />
      <details className="op-table"><summary>精确元件位置与模场数据</summary><p>表中波前 R 为元件后的空气等效值；曲线中的分段波前 R 按所在介质显示。</p><div className="wb-table-wrap"><table><thead><tr><th>平面 / 元件</th><th>z / mm</th><th>w / μm</th><th>空气等效 R / mm</th></tr></thead><tbody>{Object.entries(analysis.planes).flatMap(([plane, result]) => result.elements.map((p, i) => <tr key={`${plane}${i}`}><td>{plane === 'tangential' ? 'T' : 'S'} · {p.name}</td><td>{p.z_mm.toFixed(4)}</td><td>{(p.radius_mm * 1000).toFixed(4)}</td><td>{p.curvature_mm == null ? '∞' : p.curvature_mm.toFixed(4)}</td></tr>))}</tbody></table></div></details>
      </details>
      {draft.system.mode !== 'single_pass' && <section className="op-map"><h3>二维稳定图</h3><p>扫描两个自由参数，查看 T/S 均稳定的区域；修改工程后请先保存。</p><details className="op-scan-config" open={!map || undefined}><summary>扫描设置 · X {map?.x_axis.start ?? x.start}—{map?.x_axis.stop ?? x.stop} / Y {map?.y_axis.start ?? y.start}—{map?.y_axis.stop ?? y.stop}</summary><div className="op-axes">{axisEditor(x, setX, 'X')}{axisEditor(y, setY, 'Y')}</div><button className="btn btn-primary" disabled={busy || dirty} onClick={scan}>计算并保存二维扫描</button></details>{map && <><OpticalScanView scan={map} system={current.project.system} recordLabel={'记录 #' + map.artifact_id} /><button className="btn btn-secondary" onClick={() => download(`stability-map-${map.artifact_id}.json`, map)}>导出完整扫描数据</button></>}</section>}
    </>}
  </section>;
}
