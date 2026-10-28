import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { casesApi } from '../api/cases';
import ExperimentWorkbench from '../components/ExperimentWorkbench';
import LegacyAgentWorkspace from './LegacyAgentWorkspace';

export default function AgentWorkspace() {
  const [cases, setCases] = useState([]);
  const [caseId, setCaseId] = useState('');
  const [caseData, setCaseData] = useState(null);
  const [legacy, setLegacy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { casesApi.list().then(setCases).catch(e => setError(e.message)); }, []);
  useEffect(() => {
    let alive = true;
    if (caseId) casesApi.get(caseId).then(data => { if (alive) setCaseData(data); }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [caseId]);
  return <div><div className="detail-header"><div><h1>实验 Agent</h1><p className="muted">围绕任务理解、计算、查证与追问；工具由 Agent 按需选择。</p></div><div className="action-row"><Link className="btn btn-primary" to="/cases/new">＋ 新建任务</Link><button className="btn btn-secondary" onClick={() => setLegacy(v => !v)}>{legacy ? '返回任务工作区' : '旧版对话记录'}</button></div></div>
    {error && <p role="alert" className="error">{error}</p>}
    {legacy ? <LegacyAgentWorkspace /> : <><div className="card" style={{ marginBottom: 24 }}><label htmlFor="agent-case">选择一个案例继续工作</label><select id="agent-case" value={caseId} onChange={e => setCaseId(e.target.value)} style={{ marginLeft: 14, maxWidth: '100%' }}><option value="">选择案例…</option>{cases.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}</select>{caseId && <Link to={`/cases/${caseId}`} style={{ marginLeft: 16 }}>打开案例 →</Link>}</div>
      {caseData?.id === Number(caseId) ? <ExperimentWorkbench key={caseData.id} caseData={caseData} /> : <div className="wb-empty"><div className="wb-orbit">λ</div><h3>把你要解决的问题带进来。</h3><p>可以是一个设计目标、一段测量数据、一组已有元件，或一个尚未解释的实验现象。新建任务只需要标题和描述。</p><Link to="/cases/new">开始一个新任务 →</Link></div>}</>}
  </div>;
}
