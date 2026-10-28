import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { workbenchApi } from '../api/workbench';
import { casesApi } from '../api/cases';
import DesignWorkspace from './DesignWorkspace';
import OpticalProject from './OpticalProject';
import ScientificPlot from './ScientificPlot';
import OpticalFieldView from './OpticalFieldView';
import OpticalScanView, { opticalParameterLabels } from './OpticalScanView';
import AgentText from './AgentText';
import './OpticalAnalysis.css';
import './ExperimentWorkbench.css';

const states = { pending: '排队中', running: '正在工作', completed: '本轮已完成', partial: '已有部分结果', needs_input: '需要你补充', unsupported: '当前工具有边界', failed: '运行中断', cancelled: '已停止' };
const names = { read_optical_project: '读取光学工程', save_optical_project: '保存并计算工程', import_design_project: '导入光学工程', scan_optical_system_2d: '二维稳定图', fit_beam_caustic: '拟合实测焦散', analyze_saved_design: '精确复算已存方案', read_tool_result: '读取已存计算', list_inventory: '查阅元件库', read_attachment: '读取附件', read_artifact: '回看已有结果', read_history: '回看对话', search_knowledge: '检索知识库', search_literature: '检索文献', analyze_optical_system: '计算光学系统', scan_optical_system: '扫描光学参数', fit_power_curve: '拟合功率数据', compute_phase_match: '计算相位匹配', match_components: '匹配元件规格', compute_coating: '分析镀膜', design_linear_laser: '求解端泵平凹腔', inspect_tool: '查看工具能力', finish: '整理结论与下一步' };
const bullets = (items, className) => !!items?.length && <ul className={className}>{items.map((text, i) => <li key={i}>{text}</li>)}</ul>;
const saveJSON = (name, value) => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};

function NumericalResult({ call }) {
  const plot = useRef(null);
  const [plotError, setPlotError] = useState('');
  const output = call.output?.analysis?.planes ? call.output.analysis : call.output || {};
  const chart = useMemo(() => {
    if (output.maps) return { x: `元件 ${output.x_axis.element_index + 1} · ${output.x_axis.parameter}`, y: `元件 ${output.y_axis.element_index + 1} · ${output.y_axis.parameter}`, data: [{ type: 'heatmap', x: output.x, y: output.y, z: output.maps.stable_both, colorscale: [[0, '#483446'], [1, '#78c9b5']], zmin: 0, zmax: 1 }] };
    if (call.name === 'fit_beam_caustic' && output.data) return { x: '测量位置 / mm', y: '光束半径 / mm', data: [{ type: 'scatter', mode: 'markers', x: output.data.z_mm, y: output.data.radius_mm, name: '测量数据' }, { type: 'scatter', mode: 'lines', x: output.data.z_mm, y: output.data.fit_radius_mm, name: '二次焦散拟合' }] };
    if (output.analysis?.trace) return { x: '沿光路物理位置 / mm', y: '1/e² 光束半径 / mm', data: [
      { x: output.analysis.trace.points.map(p => p.z_mm), y: output.analysis.trace.points.map(p => p.w_mm), type: 'scatter', mode: 'lines', name: output.analysis.mode === 'pump' ? '泵浦等效场景' : '腔模 T=S', line: { color: '#80d6c5', width: 2 } },
      { x: output.analysis.trace.waists.map(p => p.z_mm), y: output.analysis.trace.waists.map(p => p.w_mm), type: 'scatter', mode: 'markers', name: '解析束腰', marker: { color: '#d5aa73', size: 8 } },
    ] };
    if (output.planes) return { x: '沿光路物理位置 / mm', y: '1/e² 光束半径 / mm', data: Object.entries(output.planes).map(([plane, result], i) => ({ x: result.samples?.map(p => p.z_mm) || [], y: result.samples?.map(p => p.radius_mm) || [], type: 'scatter', mode: 'lines', name: plane === 'tangential' ? '切向 T' : '弧矢 S', line: { color: i ? '#d5aa73' : '#80d6c5', width: 2, dash: i ? 'dash' : 'solid' } })) };
    if (call.name === 'scan_optical_system') {
      const cavity = output.points?.some(p => p.tangential?.m != null);
      return { x: `${output.element} · ${opticalParameterLabels[output.parameter] || output.parameter}`, y: cavity ? '往返矩阵 m = (A+D)/2' : '输出面 1/e² 半径 / mm', data: ['tangential', 'sagittal'].map((plane, i) => ({ x: output.points?.map(p => p.value), y: output.points?.map(p => (cavity ? p[plane]?.m : p[plane]?.output?.radius_mm) ?? null), type: 'scatter', mode: 'lines', name: i ? '弧矢 S' : '切向 T', line: { color: i ? '#d5aa73' : '#80d6c5', dash: i ? 'dash' : 'solid' } })) };
    }
    if (call.name === 'fit_power_curve' && output.data) return { x: '泵浦功率 / W', y: '输出功率 / W', data: [{ x: output.data.pump_w, y: output.data.output_w, type: 'scatter', mode: 'markers', name: '输入测量', marker: { color: '#80d6c5', size: 8 } }, ...(output.fit_line ? [{ x: output.data.pump_w, y: output.data.pump_w.map(p => Math.max(0, output.fit_line.a * p + output.fit_line.b)), type: 'scatter', mode: 'lines', name: '分段拟合', line: { color: '#d5aa73' } }] : [])] };
    return null;
  }, [output, call.name]);
  const layout = useMemo(() => ({ autosize: true, height: 370, margin: { l: 75, r: 25, t: 25, b: 85 }, paper_bgcolor: '#131d2a', plot_bgcolor: '#131d2a', font: { color: '#d0deeb', size: 12 }, xaxis: { title: { text: chart?.x.length > 52 ? chart.x.slice(0, 42) + '… · ' + (opticalParameterLabels[output.parameter] || output.parameter) : chart?.x }, gridcolor: '#ffffff0d', zerolinecolor: '#ffffff20' }, yaxis: { title: { text: chart?.y }, gridcolor: '#ffffff0d', zerolinecolor: '#ffffff20' }, legend: { orientation: 'h', x: 0, y: 1.14 }, hovermode: 'x unified',
    shapes: chart?.y.startsWith('往返矩阵') ? [-1, 1].map(value => ({ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: value, y1: value, line: { color: '#d1ad75', width: 1, dash: 'dot' } })) : [],
  }), [chart, output.parameter]);
  if (output.planes) return <OpticalFieldView analysis={output} revisionLabel={'工具 #' + call.id} />;
  if (output.maps) return <OpticalScanView scan={output} system={call.input?.system} recordLabel={'工具 #' + call.id} />;
  if (!chart || !chart.data.some(d => d.y?.some(v => v != null))) return null;
  return <section className="wb-numerical"><div className="wb-row"><h3>{names[call.name]} <small>工具 #{call.id}</small></h3><button className="btn btn-secondary" onClick={() => plot.current?.exportImage('svg').catch(e => setPlotError(e.message))}>导出 SVG</button></div>
    {plotError && <p role="alert" className="wb-error">{plotError}</p>}
    {output.stable_both_planes !== undefined && <p className="wb-engine">{output.stable_both_planes ? 'T / S 双平面稳定' : '存在失稳或临界平面，无受限基模'}</p>}
    <ScientificPlot ref={plot} data={chart.data} layout={layout} filename={`task-tool-${call.id}`} />
    {chart.y.startsWith('往返矩阵') && <p className="field-caption">虚线为m=±1稳定边界；|m|&lt;1为几何稳定。扫描曲线不代表输出功率或效率。</p>}
    {output.analysis?.trace?.waists?.map((p, i) => <p className="wb-engine" key={i}>解析束腰 z={p.z_mm.toFixed(5)} mm · w={(p.w_mm * 1000).toFixed(3)} μm · 瑞利长度 {p.z_R_mm.toFixed(5)} mm</p>)}
    {!!output.planes && <div className="wb-table-wrap"><table><thead><tr><th>元件 / 平面</th><th>z / mm</th><th>半径 w / mm</th><th>波前 R / mm</th></tr></thead><tbody>{Object.entries(output.planes).flatMap(([plane, data]) => (data.elements || []).map((node, i) => <tr key={`${plane}-${i}`}><td>{node.name} · {plane === 'tangential' ? 'T' : 'S'}</td><td>{node.z_mm.toFixed(3)}</td><td>{node.radius_mm.toPrecision(5)}</td><td>{node.curvature_mm == null ? '∞' : node.curvature_mm.toPrecision(5)}</td></tr>))}</tbody></table></div>}
    {call.name === 'fit_power_curve' && <div className="wb-metrics"><span>阈值 <b>{output.threshold_pump} W</b></span><span>斜率效率 <b>{output.slope_efficiency_pct}%</b></span><span>拟合 R² <b>{output.r_squared}</b></span></div>}
    {bullets(output.warnings)}<small className="wb-engine">{output.engine || (typeof output.scope === 'string' ? output.scope : '图表直接读取工具输出')}{output.engine && ' · 近轴模型，元件坐标按传播方向展开'}</small>
  </section>;
}

function ToolTrace({ call }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={event => { if (event.currentTarget === event.target) setOpen(event.currentTarget.open); }} className={`wb-tool ${call.status}`}><summary><span>{call.status === 'running' ? '◌' : call.status === 'failed' ? '!' : '✓'}</span><strong>{names[call.name] || call.name}</strong><small>#{call.id} · {states[call.status] || call.status}{call.latency_ms != null ? ` · ${(call.latency_ms / 1000).toFixed(1)} s` : ''}</small></summary>
    {open && <><p>{call.input?.purpose}</p>{call.error && <p className="wb-error">{call.error}</p>}<NumericalResult call={call} />
    <div className="wb-row"><small>输入、输出及来源均保留，可复核</small><button className="btn btn-secondary" onClick={() => saveJSON(`tool-${call.id}.json`, call)}>下载计算记录</button></div>
    <details><summary>输入参数</summary><pre>{JSON.stringify(call.input, null, 2)}</pre></details><details><summary>完整工具输出</summary><pre>{JSON.stringify(call.output, null, 2)}</pre></details>
  </>}</details>;
}

function NumericalResults({ calls }) {
  const [selected, setSelected] = useState(null);
  const ready = calls.filter(call => call.status === 'completed' && ['analyze_optical_system', 'analyze_saved_design', 'scan_optical_system', 'scan_optical_system_2d', 'fit_beam_caustic', 'save_optical_project', 'import_design_project', 'fit_power_curve'].includes(call.name));
  const preferred = [...ready].reverse().find(call => call.output?.analysis?.planes || call.output?.planes) || ready.at(-1);
  const current = ready.find(call => call.id === selected) || preferred;
  if (!current) return <p className="wb-muted">本轮尚无计算曲线。Agent 执行物理工具后，光场和扫描结果会显示在这里。</p>;
  return <section className="wb-plots"><label>选择本轮计算结果<select aria-label="本轮计算曲线" value={current.id} onChange={event => setSelected(Number(event.target.value))}>{ready.map(call => <option key={call.id} value={call.id}>{names[call.name]} · #{call.id}{call.input?.purpose ? ' · ' + call.input.purpose.slice(0, 44) : ''}</option>)}</select></label><p className="field-caption">{current.input?.purpose}</p><p className="wb-engine">每张图对应独立工具记录；不同晶体朝向、冷热腔与参数扫描不会相互覆盖。</p><NumericalResult call={current} /></section>;
}

export default function ExperimentWorkbench({ caseData, onArtifactsChanged }) {
  const id = caseData.id;
  const [state, setState] = useState(null);
  const [message, setMessage] = useState('');
  const [selected, setSelected] = useState([]);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('result');
  const [focused, setFocused] = useState(false);
  const [runId, setRunId] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const input = useRef(null);
  const scroll = useRef(null);
  const alive = useRef(true);
  const latest = state?.runs?.[0];
  const busy = sending || latest?.active || ['pending', 'running'].includes(latest?.status);
  const current = (runId && runDetail?.id === runId && runId !== latest?.id ? runDetail : state?.runs?.find(r => r.id === runId)) || latest;
  const result = current?.result;
  const tools = current?.tools?.filter(c => c.name !== 'finish') || [];

  const refresh = async () => { const data = await workbenchApi.get(id); if (alive.current) setState(data); return data; };
  useEffect(() => {
    if (latest?.final_content_id && onArtifactsChanged) onArtifactsChanged().catch(e => setError(e.message));
  }, [latest?.final_content_id]);
  useEffect(() => {
    alive.current = true;
    workbenchApi.get(id).then(data => { if (alive.current) setState(data); }).catch(e => { if (alive.current) setError(e.message); });
    return () => { alive.current = false; };
  }, [id]);
  useEffect(() => {
    if (!runId || runId === latest?.id) return;
    let active = true;
    workbenchApi.getRun(id, runId).then(data => { if (active) setRunDetail(data); }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [id, runId, latest?.id]);
  useEffect(() => {
    if (!busy) return;
    let active = true;
    const timer = setInterval(() => workbenchApi.get(id).then(data => { if (active) setState(data); }).catch(e => { if (active) setError(e.message); }), 2000);
    return () => { active = false; clearInterval(timer); };
  }, [id, busy]);
  useEffect(() => { if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight; }, [state?.messages?.length]);
  const seed = text => { setMessage(text); setTab('result'); input.current?.focus(); };
  const send = async e => {
    e.preventDefault(); if (busy || uploading || !message.trim()) return;
    setSending(true); setError(''); setRunId(null); setTab('result');
    try { await workbenchApi.run(id, message.trim(), selected); setMessage(''); setSelected([]); await refresh(); }
    catch (err) { setError(err.message); } finally { setSending(false); }
  };
  const upload = async e => {
    const files = Array.from(e.target.files || []); e.target.value = ''; setUploading(true); setError('');
    try { for (const file of files.slice(0, 8 - selected.length)) { const item = await casesApi.uploadAttachment(id, file); setSelected(prev => [...prev, item.id]); } await refresh(); }
    catch (err) { setError(err.message); } finally { setUploading(false); }
  };
  return <div className={"wb-workspace" + (focused ? " is-focused" : "")}>
    {!focused && <aside className="wb-conversation"><div className="wb-heading"><span>LASERCLAW · LAB AGENT</span><h2>从任务出发</h2><p>目标、手头的信息、已有元件，都可以直接告诉我。</p></div>
      <div className="wb-messages" ref={scroll} aria-live="polite">{!state?.messages?.length && <div className="wb-welcome"><b>不必先把参数填齐。</b><p>我会先判断哪些问题可以计算，按需查元件、读资料、建模和比较方案。需要你补充时，会说明缺什么、为什么需要，以及怎么获得。</p><button className="btn btn-secondary" onClick={() => seed(`请根据本案例标题和描述推进任务：${caseData.title}\n${caseData.description || ''}`)}>从案例标题与描述开始 →</button></div>}
        {state?.messages?.map(m => <article className={`wb-message ${m.role}`} key={m.id}><small>{m.role === 'user' ? '你' : 'Agent'}</small><AgentText>{m.role === 'assistant' && m.metadata?.workbench_run_id && m.content.length > 500 ? `${m.content.slice(0, 500)}…` : m.content}</AgentText>{!!m.metadata?.attachment_ids?.length && <small>引用 {m.metadata.attachment_ids.length} 个附件</small>}{m.metadata?.workbench_run_id && m.role === 'assistant' && <button onClick={() => { setRunId(m.metadata.workbench_run_id); setTab('result'); }}>查看本轮结果 ↗</button>}</article>)}
      </div>
      {latest && <div className="wb-progress" role="status"><div className="wb-row"><strong>{states[latest.status]}</strong>{busy && <button onClick={() => workbenchApi.stop(id, latest.id).then(refresh).catch(e => setError(e.message))}>停止</button>}</div><p>{names[latest.steps?.at(-1)?.title] || latest.steps?.at(-1)?.title || '读取案例上下文'} · {latest.steps?.at(-1)?.purpose}</p></div>}
      <form onSubmit={send} className="wb-composer"><label htmlFor={`wb-message-${id}`}>需求、补充信息或追问</label><textarea id={`wb-message-${id}`} ref={input} rows={5} value={message} maxLength={24000} onChange={e => setMessage(e.target.value)} placeholder="例如：已有这几件元件，帮我比较两种光路；或上传测量数据，分析问题出在哪里。" />
        {!!state?.attachments?.length && <details><summary>附件 · 已选 {selected.length}/8</summary><div className="wb-attachments">{state.attachments.map(a => <label key={a.id}><input type="checkbox" checked={selected.includes(a.id)} disabled={busy || uploading || (!selected.includes(a.id) && selected.length >= 8)} onChange={() => setSelected(prev => prev.includes(a.id) ? prev.filter(x => x !== a.id) : [...prev, a.id])} />{a.filename}</label>)}</div></details>}
        <div className="wb-row"><label className="btn btn-secondary wb-upload">{uploading ? '上传中…' : '＋ 资料 / 数据 / 图片'}<input type="file" multiple disabled={busy || uploading || selected.length >= 8} onChange={upload} /></label><button className="btn btn-primary" disabled={busy || uploading || !message.trim()}>{busy ? '工作中…' : '交给 Agent →'}</button></div>
        <small className="wb-engine">可读取案例信息与元件库 · 计算过程与结果自动保存</small>
      </form>{error && <div className="wb-error" role="alert">{error}<button onClick={() => refresh().then(() => setError('')).catch(e => setError(e.message))}>重新连接</button></div>}
    </aside>}
    <main className="wb-results"><div className="wb-result-header"><div><span className="wb-eyebrow">任务工作区</span><h2>结果、依据与下一步</h2></div><button className="btn btn-secondary wb-focus" onClick={() => setFocused(value => !value)}>{focused ? "显示对话" : "展开结果区"}</button>{!!state?.runs?.length && <select aria-label="任务轮次" value={current?.id || ''} onChange={e => setRunId(Number(e.target.value))}>{state.runs.map(r => <option key={r.id} value={r.id}>第 #{r.id} 轮 · {states[r.status]}</option>)}</select>}</div>
      <div className="wb-tabs">{[['result', '任务结果'], ['fields', '光场与扫描'], ['project', '光学工程'], ['tools', `工具过程${tools.length ? ` · ${tools.length}` : ''}`], ['designs', '历史专用设计']].map(([key, label]) => <button key={key} className={tab === key ? 'active' : ''} onClick={() => { setTab(key); if (['fields', 'project'].includes(key)) setFocused(true); }}>{label}</button>)}</div>
      {tab === 'fields' ? <NumericalResults key={current?.id || 0} calls={tools} /> : tab === 'project' ? <OpticalProject key={`${id}-${latest?.final_content_id || 0}`} caseId={id} onAsk={seed} pending={busy} /> : tab === 'designs' ? <><p className="field-note">这是历史端泵专用设计，保留当时的晶体尺寸和假设。当前布置以最新光学工程及本轮计算为准，历史版本不会自动改写。</p><DesignWorkspace key={`${id}-${latest?.final_content_id || 0}`} caseData={caseData} savedOnly onAsk={seed} /></> : tab === 'tools' ? <div className="wb-trace">{!tools.length && <p className="wb-muted">Agent 调用工具后，会在这里显示每一步的目的、参数与真实返回结果。</p>}{tools.map(c => <ToolTrace key={c.id} call={c} />)}</div> : <>
        {!current && <section className="wb-empty"><div className="wb-orbit">λ</div><h3>一个目标，多种解法。</h3><p>你提出问题，Agent 组织工作。需要什么能力，就调用什么工具。</p><div className="wb-capability-grid">{[['光路与谐振腔', '传播、稳定性、参数扫描'], ['元件与方案', '查库存、核规格、比较取舍'], ['实验与数据', '拟合曲线、解释结果、指导补测'], ['文献与资料', '读取附件、检索依据、识别缺口']].map(([a, b]) => <div key={a}><strong>{a}</strong><small>{b}</small></div>)}</div><p>任务不必一次解决。每次补充，都会成为下一轮工作的上下文。</p><Link to="/inventory">查看元件库 →</Link></section>}
        {current && !result && <section className="wb-pending"><span className="wb-eyebrow">{states[current.status]}</span><h3>{current.goal.split("\n")[0].slice(0, 140)}</h3><details className="wb-goal"><summary>展开完整任务与约束</summary><p>{current.goal}</p></details><p>{current.steps?.at(-1)?.purpose || 'Agent 正在读取案例与已有信息。'}</p>{tools.map(c => <ToolTrace key={c.id} call={c} />)}{current.status === 'failed' && <button className="btn btn-secondary" onClick={() => seed(`请继续上一轮任务，复用已保存的工具结果。\n${current.goal}`)}>继续任务</button>}</section>}
        {result && <><section className="wb-answer"><div className="wb-row"><span className={`wb-status ${result.status}`}>{states[result.status]}</span><button className="btn btn-secondary" onClick={() => saveJSON(`case-${id}-run-${current.id}.json`, current)}>导出本轮记录</button></div><details className="wb-goal"><summary>本轮目标</summary><p>{current.goal}</p></details><AgentText>{result.summary}</AgentText>{bullets(result.findings, 'wb-findings')}
          {!!result.assumptions?.length && <details><summary>采用的假设 · {result.assumptions.length}</summary>{bullets(result.assumptions)}</details>}
          {!!result.facts?.length && <details><summary>事实与来源 · {result.facts.length}</summary>{result.facts.map((f, i) => <p key={i}><small>{({ user_stated: '用户提供', document: '资料读取', calculated: '工具计算', hypothesis: '待验证假设' })[f.kind]} · {f.source}</small><br />{f.statement}</p>)}</details>}
          {!!result.evidence_tool_call_ids?.length && <p className="wb-evidence">计算与检索依据 {result.evidence_tool_call_ids.map(n => <button key={n} onClick={() => setTab('tools')}>工具 #{n}</button>)}</p>}
        </section>
        {!!result.questions?.length && <section className="wb-questions"><span className="wb-eyebrow">补充后继续</span><h3>下一步需要的信息</h3>{result.questions.map((q, i) => <article key={i}><h4>{q.question}</h4><p>{q.why}</p><div><strong>怎么获得</strong><p>{q.how_to_obtain}</p></div><small>回复格式：{q.expected_format}</small><button className="btn btn-secondary" onClick={() => seed(`关于「${q.question}」：\n`)}>补充这项信息 →</button></article>)}</section>}
        <NumericalResults key={current.id} calls={tools} />
        {!!result.next_steps?.length && <section className="wb-next"><h3>建议接下来做</h3>{bullets(result.next_steps)}<button className="btn btn-secondary" onClick={() => seed('继续推进当前任务，复用已有结果。能用现有信息完成的部分请直接执行，需要我提供的信息请明确说明。')}>继续推进 →</button></section>}
        </>}
      </>}
      <details className="wb-capabilities"><summary>当前可调用的工具与计算边界</summary><p>Agent 按任务选择工具。光学工具当前运行 Python / NumPy ABCD，尚未连接 Rezonator C++ 程序。</p>{state?.capabilities?.map(c => <p key={c.name}><b>{names[c.name] || c.name}</b><br /><small>{c.description}</small></p>)}</details>
    </main>
  </div>;
}
