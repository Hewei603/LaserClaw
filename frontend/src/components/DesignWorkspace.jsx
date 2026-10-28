import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { casesApi } from '../api/cases';
import { designApi } from '../api/design';
import './DesignWorkspace.css';
import OpticalAnalysis from './OpticalAnalysis';

const fmt = (value, digits = 2) => value == null ? '待补参数' : Number(value).toLocaleString('zh-CN', { maximumFractionDigits: digits });
const mirrorText = r => r == null ? '平面' : `凹面 R${fmt(r, 0)} mm`;
const valueText = fact => `${Array.isArray(fact.value) ? fact.value.join(' / ') : ({ fiber: '光纤输出', linear: '直线腔', true: '是', false: '否' }[String(fact.value)] || fact.value)} ${fact.unit || ''}`;

function Layout({ candidate }) {
  const nodes = candidate.positions.filter(p => !['active', 'pump_focus'].includes(p.id));
  return <div className="design-path" aria-label="全光路元件顺序">{nodes.map((p, index) => <React.Fragment key={p.id}>
    {index > 0 && <span className="design-path-arrow">→</span>}
    <div className={`design-path-node ${p.z_mm == null ? 'pending' : ''}`}><span>{String(index + 1).padStart(2, '0')}</span><strong>{p.name}</strong><small>{p.z_mm == null ? '位置待补参数' : `z ${fmt(p.z_mm)} mm`}</small></div>
  </React.Fragment>)}</div>;
}

function Constraints({ facts, inventory, patch, onChange, disabled }) {
  const val = key => Object.hasOwn(patch, key) ? patch[key] ?? '' : facts?.[key]?.value ?? '';
  const update = (key, value) => onChange(prev => ({ ...prev, [key]: value }));
  return <details className="design-constraints"><summary>已有元件 / 固定位置 / 设计约束{Object.keys(patch).length ? ' · 有待计算修改' : ''}</summary>
    <p>已装好的器件可锁定。留空表示交给求解器；坐标统一相对 M1 镀膜面，泵浦侧为负值。</p>
    {[['collimator', '准直镜', 'lens'], ['focus_lens', '聚焦镜', 'lens'], ['crystal', '增益晶体', 'gain_crystal'], ['M1', '输入镜 M1', 'mirror'], ['M2', '输出镜 M2', 'mirror']].map(([role, label, category]) => <label key={role}>{label} · 库存绑定<select aria-label={`${label}库存绑定`} disabled={disabled} value={val(`${role}_inventory_id`)} onChange={e => update(`${role}_inventory_id`, e.target.value ? Number(e.target.value) : null)}><option value="">自动选型 / 使用对话中的已有器件</option>{inventory.filter(i => i.category === category).map(i => <option key={i.id} value={i.id} disabled={i.condition === 'damaged' || i.available_quantity < 1}>#{i.id} {i.name} · 可用 {i.available_quantity}</option>)}</select></label>)}
    {!inventory.length && <small>元件库当前为空；已有器件可直接在对话中描述。<Link to="/inventory">导入元件库 →</Link></small>}
    <div className="design-constraint-grid">{[
      ['crystal_front_mm', 'M1 → 晶体前端面 / mm'], ['output_gap_mm', '晶体后端面 → M2 / mm'],
      ['input_roc_mm', '固定 M1 曲率 R / mm'], ['output_roc_mm', '固定 M2 曲率 R / mm'], ['oc_transmission_pct', '固定输出镜 T / %'],
      ['pump_focus_depth_mm', '焦点距晶体前端面 / mm'], ['target_mode_radius_um', '目标模半径 / μm'],
      ['collimator_f_mm', '准直镜实测 f / mm'], ['focus_f_mm', '聚焦镜 f / mm'],
      ['focus_lens_z_mm', '固定聚焦镜 z / mm'], ['collimator_z_mm', '固定准直镜 z / mm'], ['source_z_mm', '固定光纤端 z / mm'],
      ['min_output_gap_mm', 'M2 最小间隙 / mm'], ['max_output_gap_mm', 'M2 最大间隙 / mm'],
    ].map(([key, label]) => <label key={key}>{label}<input type="number" step="any" aria-label={label} disabled={disabled} placeholder="由求解器设计" value={val(key)} onChange={e => update(key, e.target.value === '' ? null : Number(e.target.value))} /></label>)}</div>
    <label className="design-check"><input type="checkbox" disabled={disabled} checked={Boolean(val('input_mirror_near_crystal'))} onChange={e => update('input_mirror_near_crystal', e.target.checked)} />输入镜靠近晶体（未指定时用 3 mm 间隙）</label>
  </details>;
}

function Bom({ items }) {
  return <div className="design-bom">{items.map(item => <article key={item.role}>
    <div className="design-card-heading"><h4>{item.role === 'M1' ? '输入腔镜 M1' : '输出耦合镜 M2'}</h4><span className={`design-pill ${item.status === 'in_stock' ? 'good' : 'warn'}`}>{{ in_stock: '有规格匹配库存', verify_or_buy: '库存待核验 / 采购', purchase: '采购缺口', owned: '已拥有 · 保留实物' }[item.status]}</span></div>
    <p>{item.spec}</p>{item.coating_basis && <small>{item.coating_basis}</small>}<p>有效通光口径 ≥ {fmt(item.min_clear_aperture_mm)} mm</p>
    {item.role === 'M2' && <p>透过率：{item.transmission_pct ? `${item.transmission_pct}%` : `${item.transmission_candidates_pct.join(' / ')}% 场景待比较（实物未知）`}</p>}
    {item.matched.map(part => <div className="design-stock" key={part.id}><Link to={`/inventory?search=${encodeURIComponent(part.name)}`}>{part.name}</Link><small>可用 {part.available_quantity} · {part.location || '库位未填'}</small><p>{part.raw_spec}</p></div>)}
    {!!item.needs_verification.length && <details><summary>待核验库存（{item.counts.needs_verification}）</summary>{item.needs_verification.map(part => <div className="design-stock" key={part.id}><strong>{part.name}</strong><p>{part.unknowns.join('；')}</p><small>{part.raw_spec}</small></div>)}</details>}
    {!!item.rejected.length && <details><summary>已排除库存（{item.counts.rejected}）</summary>{item.rejected.map(part => <p key={part.id}>{part.name}：{part.reasons.join('；')}</p>)}</details>}
  </article>)}</div>;
}

export default function DesignWorkspace({ caseData, savedOnly = false, onAsk }) {
  const [state, setState] = useState(null);
  const [revisionId, setRevisionId] = useState(null);
  const [rank, setRank] = useState(null);
  const [message, setMessage] = useState(caseData.description || '');
  const [images, setImages] = useState([]);
  const [selected, setSelected] = useState([]);
  const [sending, setSending] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [constraints, setConstraints] = useState({});
  const inputRef = useRef(null);
  const lastMessageRef = useRef(null);
  const id = caseData.id;
  const latestRun = state?.runs?.[0];
  const busy = sending || ['pending', 'running'].includes(latestRun?.status);
  const refresh = async () => {
    const data = await designApi.get(id);
    setState(data);
    return data;
  };
  useEffect(() => {
    let alive = true;
    Promise.all([designApi.get(id), casesApi.listAttachments(id)]).then(([data, attachments]) => {
      if (!alive) return;
      setState(data); setImages(attachments.filter(a => /\.(png|jpe?g|webp)$/i.test(a.filename)));
      if (data.messages.length) setMessage('');
    }).catch(err => { if (alive) setError(err.message); });
    return () => { alive = false; };
  }, [id]);
  useEffect(() => {
    if (!busy) return;
    let alive = true;
    let timer;
    const poll = async () => {
      try { const data = await designApi.get(id); if (alive) { setState(data); setError(''); } }
      catch (err) { if (alive) setError(err.message); }
      if (alive) timer = setTimeout(poll, 1800);
    };
    timer = setTimeout(poll, 1000);
    return () => { alive = false; clearTimeout(timer); };
  }, [busy, id]);
  useEffect(() => {
    const container = lastMessageRef.current?.parentElement;
    if (container) container.scrollTop = container.scrollHeight;
  }, [state?.messages?.length]);
  const revision = state?.revisions.find(r => r.id === revisionId) || state?.revisions[0];
  const design = revision?.content.engineering_design;
  const candidate = design?.candidates.find(c => c.rank === rank) || design?.candidates[(design?.selected_rank || 1) - 1];
  const runDesign = async (text, patch = constraints) => {
    if (busy || uploading) return;
    setSending(true); setError('');
    try {
      const run = await designApi.run(id, text, selected, patch);
      setMessage(''); setSelected([]); setRevisionId(null); setRank(null); setConstraints({});
      setState(prev => ({ ...prev, runs: [{ id: run.task_id, status: 'pending', steps: [] }, ...(prev?.runs || [])] }));
      await refresh();
    } catch (err) { setError(err.message); } finally { setSending(false); }
  };
  const send = event => {
    event.preventDefault();
    runDesign(message.trim() || '根据案例标题、描述、已知条件和元件库，补齐缺失器件并优化全光路；固定本次面板指定的条件，输出仿真和元件位置。');
  };
  const upload = async event => {
    const files = Array.from(event.target.files || []);
    event.target.value = '';
    if (!files.length) return;
    setUploading(true); setError('');
    try {
      for (const file of files.slice(0, 4 - selected.length)) {
        const attachment = await casesApi.uploadAttachment(id, file);
        setImages(prev => [...prev, attachment]); setSelected(prev => [...prev, attachment.id]);
      }
    } catch (err) { setError(err.message); } finally { setUploading(false); }
  };
  const seed = text => { if (onAsk) { onAsk(text); return; } setMessage(text); inputRef.current?.focus(); };
  return <div className={`design-workspace ${savedOnly ? 'saved-only' : ''}`}>
    {!savedOnly && <aside className="design-conversation">
      <div className="design-section-title"><span className="design-eyebrow">DESIGN AGENT</span><h2>把实验目标交给 Agent</h2><p>需求 → 数值计算 → 库存选型 → 光路位置</p></div>
      <div className="design-messages" aria-live="polite">
        {!state?.messages.length && <div className="design-welcome"><strong>从实验目标出发，补齐整条光路。</strong><p>直接按标题和描述开始；已有元件写在对话里，或在下方绑定库存、固定位置。Agent 选择缺失器件，再由物理内核计算和排序。</p><small>当前自动求解范围：端泵平凹直线腔、双透镜光纤成像。设计假设与实物参数分别保存。</small></div>}
        {state?.messages.map(m => <div key={m.id} className={`design-message ${m.role}`}><small>{m.role === 'user' ? '你' : '设计 Agent'}</small><p>{m.content}</p>{m.metadata?.attachment_ids?.length > 0 && <small>附 {m.metadata.attachment_ids.length} 张标签图片</small>}</div>)}
        <div ref={lastMessageRef} />
      </div>
      {latestRun && <div className="design-progress" role="status"><strong>{busy ? '正在生成新的设计版本…' : latestRun.status === 'failed' ? '本次计算未完成，已有设计已保留' : '设计版本已保存'}</strong>{latestRun.steps.map((step, i) => <div key={i} title={step.detail}><span>{step.status === 'completed' ? '✓' : step.status === 'failed' ? '!' : '◌'}</span>{step.title}{step.status === 'failed' && <p>{step.detail}</p>}</div>)}{latestRun.status === 'failed' && <button className="btn btn-secondary" onClick={() => { seed(latestRun.goal); const msg = state.messages.find(m => m.metadata?.design_run_id === latestRun.id && m.role === 'user'); setSelected(msg?.metadata?.attachment_ids || []); }}>恢复这次输入</button>}</div>}
      <form className="design-composer" onSubmit={send}>
        <label htmlFor="design-message">告诉 Agent 你的需求或修改</label>
        <textarea id="design-message" ref={inputRef} value={message} onChange={e => setMessage(e.target.value)} rows={6} maxLength={20000} placeholder="例如：808 nm 泵浦 Nd:YVO4，获得 1064 nm 激光。已有两片透镜，请先设计腔镜与腔长。" />
        <Constraints facts={state?.facts} inventory={state?.inventory || []} patch={constraints} onChange={setConstraints} disabled={busy || uploading} />
        {!!images.length && <details className="design-image-picker" open={selected.length > 0}><summary>标签图片 · 已选 {selected.length}/4</summary>{images.map(a => <label key={a.id}><input type="checkbox" checked={selected.includes(a.id)} disabled={busy || uploading || (!selected.includes(a.id) && selected.length >= 4)} onChange={() => setSelected(prev => prev.includes(a.id) ? prev.filter(x => x !== a.id) : [...prev, a.id])} />{a.filename}</label>)}</details>}
        <div className="design-composer-actions"><label className="btn btn-secondary design-upload">{uploading ? '上传中…' : '＋ 元件标签'}<input type="file" accept="image/png,image/jpeg,image/webp" multiple disabled={busy || uploading || selected.length >= 4} onChange={upload} /></label><button className="btn btn-primary" disabled={busy || uploading}>{busy ? '计算中…' : design ? '更新设计 →' : '按目标开始设计 →'}</button></div>
        {error && <div className="alert alert-error" role="alert">{error}<button type="button" onClick={() => refresh().then(() => setError('')).catch(err => setError(err.message))}>重新连接</button></div>}
      </form>
    </aside>}
    <main className="design-results">
      <div className="design-results-header"><div><span className="design-eyebrow">OPTICAL DESIGN</span><h2>实验设计台</h2></div>{revision && <select aria-label="设计版本" value={revision.id} onChange={e => { setRevisionId(Number(e.target.value)); setRank(null); }}><option disabled>选择版本</option>{state.revisions.map((r, i) => <option value={r.id} key={r.id}>版本 {state.revisions.length - i} · {new Date(r.generated_at).toLocaleString('zh-CN')}</option>)}</select>}</div>
      {!design ? <div className="design-start"><div className="design-start-mark">λ</div><h3>先提需求，再做设计</h3><p>这里会生成可回看的设计版本，包括计算依据、腔型比较、光束包络、元件坐标和采购规格。</p><div className="design-start-grid"><span>01<br /><strong>事实与缺口</strong></span><span>02<br /><strong>扫描与比较</strong></span><span>03<br /><strong>位置与元件</strong></span></div><p className="text-muted">未知参数保留为空；可确定的部分先计算。</p></div> : <>
        <div className="design-status-line"><span className={`design-pill ${design.status === 'modeled' ? 'good' : 'warn'}`}>{{ needs_input: '约束需修正 / 目标需明确', preliminary: '方案已求解 · 含设计假设', modeled: '名义模型已计算 · 实物待核验' }[design.status]}</span><small>{revision.model} + ABCD · {fmt(revision.latency_ms / 1000, 1)} s</small></div>
        <p className="design-summary">{design.summary || revision.content.summary}</p>
        {candidate?.placement && <section className="design-placement"><span className="design-eyebrow">当前候选 · 直接定位</span><div className="design-placement-grid"><div><small>M1 → 晶体前端面</small><strong>{fmt(candidate.placement.input_gap_mm)} <em>mm</em></strong></div><div><small>晶体物理总长</small><strong>{fmt(candidate.crystal.thickness_mm)} <em>mm</em></strong></div><div><small>晶体后端面 → M2</small><strong>{fmt(candidate.placement.output_gap_mm)} <em>mm</em></strong></div></div><p>两镜间距 {fmt(candidate.length_mm)} mm · M1 {mirrorText(candidate.R1_mm)} · M2 {mirrorText(candidate.R2_mm)} · T={candidate.bom[1].transmission_pct == null ? '未知' : `${candidate.bom[1].transmission_pct}%`}<br />泵浦名义焦点：晶体前端面内 {fmt(candidate.placement.focus_depth_mm)} mm；掺杂段位于 {fmt(candidate.placement.active_start_mm - candidate.placement.crystal_front_mm)}–{fmt(candidate.placement.active_end_mm - candidate.placement.crystal_front_mm)} mm。</p><small>{design.optimization?.claim}；不是尚未建立增益模型的输出功率最优值。</small></section>}
        {!!design.issues.length && <div className="design-issues">{design.issues.map((issue, i) => <p key={i}><strong>{issue.level === 'blocking' ? '需修正' : '待核验'}</strong>{issue.text}</p>)}</div>}
        <details className="design-section"><summary>已记录的事实 · {Object.keys(design.facts).length} 项（展开核对出处）</summary><div className="design-facts">{Object.entries(design.facts).map(([key, fact]) => <div key={key}><small>{fact.label}</small><strong>{valueText(fact)}</strong><blockquote>{fact.quote}</blockquote><small>{fact.verification === 'image_reading' ? '图片读取 · 请核对' : '用户陈述'} · {fact.source}</small></div>)}</div>{design.changes?.map((change, i) => <p key={i}>本轮修订 {change.key}：{String(change.before)} → {String(change.after)}</p>)}{design.intake_notes?.map((note, i) => <p key={i} className="text-muted">{note}</p>)}</details>
        {candidate && <>
          <section className="design-section"><div className="design-card-heading"><h3>腔型候选</h3><small>{design.search.evaluated} 个几何 · {design.search.step_mm} mm 步长</small></div><p className="text-muted">{design.search.objective}</p><div className="design-candidates">{design.candidates.map(c => <button key={c.rank} className={candidate.rank === c.rank ? 'selected' : ''} onClick={() => setRank(c.rank)}><small>候选 {c.rank}{c.rank === design.selected_rank ? ' · 推荐' : ''}</small><strong>M1 {mirrorText(c.R1_mm)} / M2 {mirrorText(c.R2_mm)}</strong><span>腔长 {fmt(c.length_mm, 0)} mm</span><span>模半径 {fmt(c.mode_radius_mm * 1000, 1)} μm</span></button>)}</div></section>
          <section className="design-section"><div className="design-card-heading"><h3>全光路布局与仿真</h3><a className="btn btn-secondary" href={designApi.rezonatorUrl(id, revision.id, candidate.rank)}>导出 Rezonator 冷腔</a></div><Layout candidate={candidate} /><p className="text-muted">顺序示意，非等比例；全部坐标相对 M1 镀膜面。透镜坐标为主面位置，设计假设见下方。</p>{candidate.pump.size_mismatch && <p className="design-mismatch">现有透镜成像尺寸与腔模相差超过 3 倍。请在泵浦成像页查看；当前候选不能称为整机效率最优方案。</p>}</section>
          <OpticalAnalysis key={`${revision.id}-${candidate.rank}`} caseId={id} revisionId={revision.id} revisionNumber={state.revisions.length - state.revisions.findIndex(r => r.id === revision.id)} candidate={candidate} busy={busy} onAdoptGap={gap => savedOnly ? seed(`固定 M1 到晶体前端面 ${candidate.placement.input_gap_mm} mm、M1 ${mirrorText(candidate.R1_mm)}、M2 ${mirrorText(candidate.R2_mm)}，把 M2 到晶体后端面改为 ${gap} mm。请更新设计并与上一版比较。`) : runDesign(`固定当前 M1 间隙和 M2 曲率，把 M2 距晶体后端面改为 ${gap} mm，重新计算完整光路。`, { ...constraints, output_gap_mm: gap, input_roc_mm: candidate.R1_mm, output_roc_mm: candidate.R2_mm, input_mirror_flat: candidate.R1_mm == null, output_mirror_flat: candidate.R2_mm == null, crystal_front_mm: candidate.crystal.position_mm })} />
          <section className="design-section"><div className="design-card-heading"><h3>元件位置 / mm</h3><a className="btn btn-secondary" href={designApi.positionsUrl(id, revision.id, candidate.rank)}>导出坐标 CSV</a></div><div className="design-table-scroll"><table><thead><tr><th>元件</th><th>z 起点</th><th>z 终点</th><th>依据</th></tr></thead><tbody>{candidate.positions.map(p => <tr key={p.id}><td>{p.name}</td><td className={p.z_mm == null ? 'design-pending' : ''}>{fmt(p.z_mm)}</td><td>{p.end_z_mm == null ? '—' : fmt(p.end_z_mm)}</td><td>{p.basis}</td></tr>)}</tbody></table></div></section>
          <section className="design-section"><div className="design-card-heading"><h3>腔镜选型与采购缺口</h3><a className="btn btn-secondary" href={designApi.bomUrl(id, revision.id, candidate.rank)}>导出选型 CSV</a></div><p className="text-muted">已检查元件库 {design.inventory_count} 条记录。规格匹配仍需确认有效通光口径、镀膜面与入射角。</p><Bom items={candidate.bom} /><Link to="/inventory">打开元件库 →</Link></section>
          {!!candidate.components?.length && <section className="design-section"><h3>整条光路 · 已有器件与补齐清单</h3><div className="design-table-scroll"><table><thead><tr><th>元件</th><th>来源</th><th>规格 / 要求</th></tr></thead><tbody>{candidate.components.map(c => <tr key={c.role}><td>{c.name}</td><td>{{ owned: '沿用已有', bound: c.inventory?.mode === 'locked' ? '锁定库存' : '推荐库存', purchase: '需配备', in_stock: '库存匹配', verify_or_buy: '库存待核验' }[c.status]}{c.inventory && <small> #{c.inventory.id} {c.inventory.name}</small>}</td><td>{c.spec}</td></tr>)}</tbody></table></div></section>}
          <section className="design-section"><h3>热透镜敏感性</h3><p className="text-muted">扫描会聚热透镜场景，尚未根据 6 W 泵浦或冷却条件计算实际热焦距。</p><div className="design-thermal">{candidate.thermal_scan.map(row => <div key={row.dioptre} className={row.stable ? 'stable' : 'unstable'}><small>f {row.f_mm == null ? '∞' : row.f_mm} mm</small><strong>{row.stable ? `${fmt(row.mode_radius_mm * 1000, 0)} μm` : '不稳定'}</strong><small>m {fmt(row.m, 3)}</small></div>)}</div><p className="text-muted">稳定条件 |(A+D)/2| &lt; 1；尺寸为掺杂段中心的腔模半径。</p></section>
          <details className="design-section"><summary>输出耦合率比较 · 所需阈值增益</summary><p>{design.power_prediction.reason}</p><div className="design-table-scroll"><table><thead><tr><th>输出镜 T</th><th>其他往返损耗</th><th>所需增益 / cm⁻¹</th></tr></thead><tbody>{design.threshold_scan.map((r, i) => <tr key={i}><td>{r.T_pct}%</td><td>{r.round_trip_loss_pct}%</td><td>{r.required_gain_cm_inv}</td></tr>)}</tbody></table></div></details>
        </>}
        {!!design.questions.length && <details className="design-section"><summary>{candidate ? '进一步收敛不确定性（不阻止当前方案计算）' : '继续设计需要的目标信息'}</summary><div className="design-questions">{design.questions.map(q => <button key={q.key} title={q.why} onClick={() => seed(`${q.question}\n我的补充：`)}><strong>{q.question}</strong><small>{q.why}</small><span>补充 →</span></button>)}</div></details>}
        <details className="design-section"><summary>计算内核、优化依据与设计假设</summary>{design.engine && <p><strong>{design.engine.name} · {design.engine.implementation}</strong><br />{design.engine.rezonator}<br />{design.engine.scope}</p>}{design.search?.score_formula && <p>{design.search.score_formula}</p>}{design.assumptions.map((a, i) => <p key={i}><strong>{a.name}：{String(a.value)} {a.unit}</strong><br />{a.basis}</p>)}{design.sources.map(s => <p key={s.url}><a href={s.url} target="_blank" rel="noreferrer">{s.title}</a></p>)}{design.next_steps?.map((s, i) => <p key={i}>{i + 1}. {s}</p>)}</details>
      </>}
    </main>
  </div>;
}
