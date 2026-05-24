import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { agentApi } from '../api/agent';
import { API_BASE_URL } from '../api/client';
import { casesApi } from '../api/cases';
import { knowledgeApi } from '../api/knowledge';
import { useLanguage } from '../LanguageContext';

function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();

  const tabs = [
    ['overview', t('caseDetail.tabs.overview')],
    ['plan', t('caseDetail.tabs.plan')],
    ['troubleshooting', t('caseDetail.tabs.troubleshooting')],
    ['rezonator', t('caseDetail.tabs.rezonator')],
    ['report', t('caseDetail.tabs.report')],
    ['knowledge', t('caseDetail.tabs.knowledge')],
    ['agent', t('caseDetail.tabs.agent')],
    ['attachments', t('caseDetail.tabs.attachments')],
  ];
  const caseId = Number(id);

  const [caseData, setCaseData] = useState(null);
  const [generatedContents, setGeneratedContents] = useState({});
  const [attachments, setAttachments] = useState([]);
  const [sources, setSources] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState({});
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [agentGoal, setAgentGoal] = useState('');
  const [agentMode, setAgentMode] = useState('troubleshooting');
  const [agentRunning, setAgentRunning] = useState(false);
  const [analyzingAttachment, setAnalyzingAttachment] = useState(null);

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [caseResult, contentsResult, attachmentsResult, sourcesResult, tasksResult] = await Promise.all([
        casesApi.get(id),
        casesApi.getGeneratedContents(id),
        casesApi.listAttachments(id),
        knowledgeApi.listSources(caseId),
        agentApi.listTasks(caseId),
      ]);

      const organized = {};
      contentsResult.forEach((item) => {
        organized[item.content_type] = organized[item.content_type] || [];
        organized[item.content_type].push(item);
      });

      setCaseData(caseResult);
      setGeneratedContents(organized);
      setAttachments(attachmentsResult);
      setSources(sourcesResult);
      setTasks(tasksResult);
      setError(null);
    } catch (err) {
      setError(t('caseDetail.loadFailed') + err.message);
    } finally {
      setLoading(false);
    }
  };

  const latest = (type) => {
    const list = generatedContents[type] || [];
    return list.length > 0 ? list[0] : null;
  };

  const handleGenerate = async (type) => {
    setGenerating((prev) => ({ ...prev, [type]: true }));
    try {
      if (type === 'plan') await casesApi.generatePlan(id);
      if (type === 'rezonator') await casesApi.generateRezonator(id);
      if (type === 'troubleshooting') await casesApi.generateTroubleshooting(id);
      if (type === 'report') await casesApi.generateReport(id);
      await loadData();
    } catch (err) {
      alert(t('caseDetail.attachmentsTab.generateFailed') + err.message);
    } finally {
      setGenerating((prev) => ({ ...prev, [type]: false }));
    }
  };

  const handleSearch = async (event) => {
    event.preventDefault();
    if (!searchQuery.trim()) return;
    const response = await knowledgeApi.search({ query: searchQuery, caseId, topK: 8 });
    setSearchResults(response.results);
  };

  const handleAgentSubmit = async (event) => {
    event.preventDefault();
    if (!agentGoal.trim()) return;
    setAgentRunning(true);
    try {
      await agentApi.createTask({ caseId, goal: agentGoal, mode: agentMode });
      setAgentGoal('');
      await loadData();
      setActiveTab('agent');
    } catch (err) {
      alert(t('caseDetail.agentTab.taskFailed') + err.message);
    } finally {
      setAgentRunning(false);
    }
  };

  const handleFileUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      await casesApi.uploadAttachment(id, file);
      event.target.value = '';
      await loadData();
    } catch (err) {
      alert(t('caseDetail.attachmentsTab.uploadFailed') + err.message);
    }
  };

  const handleAnalyzeAttachment = async (attachmentId) => {
    setAnalyzingAttachment(attachmentId);
    try {
      await casesApi.analyzeAttachment(attachmentId);
      await loadData();
      setActiveTab('attachments');
    } catch (err) {
      alert(t('caseDetail.attachmentsTab.uploadFailed') + err.message);
    } finally {
      setAnalyzingAttachment(null);
    }
  };

  const isImageAttachment = (attachment) => {
    const type = attachment.file_type || '';
    const name = attachment.filename || '';
    return type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(name);
  };

  const handleDelete = async () => {
    if (!window.confirm(t('caseDetail.confirmDelete'))) return;
    await casesApi.delete(id);
    navigate('/cases');
  };

  const renderJson = (value) => (
    <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
  );

  const renderCitations = (citations = []) => {
    if (!citations.length) return null;
    return (
      <section className="generated-section">
        <h3>{t('caseDetail.citations')}</h3>
        <div className="citation-list">
          {citations.map((citation) => (
            <article key={`${citation.source_id}-${citation.chunk_id}`} className="generated-card">
              <div className="generated-card-title">
                <span>{citation.title}</span>
                <span className="meta-pill">{citation.source_type} · {citation.score}</span>
              </div>
              <p>{citation.snippet}</p>
            </article>
          ))}
        </div>
      </section>
    );
  };

  const renderGenerated = (type) => {
    const item = latest(type);
    if (!item) {
      return (
        <div className="card">
          <p>{t('caseDetail.noContent')}</p>
          <button className="btn btn-primary" disabled={generating[type]} onClick={() => handleGenerate(type)}>
            {generating[type] ? t('caseDetail.generating') : t('caseDetail.generate')}
          </button>
        </div>
      );
    }
    return (
      <div className="card">
        <h2 className="card-title">{item.content.title || item.content.summary || item.content_type}</h2>
        {item.content.disclaimer && <div className="disclaimer">{item.content.disclaimer}</div>}
        {renderCitations(item.content.citations)}
        {renderJson(item.content)}
      </div>
    );
  };

  if (loading) return <div className="loading">{t('common.loading')}</div>;
  if (error) return <div className="error">{error}</div>;
  if (!caseData) return <div className="error">{t('caseDetail.notFound')}</div>;

  return (
    <div>
      <div className="detail-header">
        <div>
          <h1>{caseData.title}</h1>
          <p className="muted">{t('caseDetail.created')}{new Date(caseData.created_at).toLocaleString()}</p>
        </div>
        <div className="action-row">
          <a href={casesApi.bundleUrl(id)} className="btn btn-secondary" target="_blank" rel="noreferrer">Export bundle</a>
          <Link to={`/cases/${id}/edit`} className="btn btn-secondary">{t('common.edit')}</Link>
          <button onClick={handleDelete} className="btn btn-danger">{t('common.delete')}</button>
        </div>
      </div>

      <div className="tab-row">
        {tabs.map(([key, label]) => (
          <button key={key} className={activeTab === key ? 'tab active' : 'tab'} onClick={() => setActiveTab(key)}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <div className="grid-2">
          <div className="card">
            <h2 className="card-title">{t('caseDetail.overview.basicInfo')}</h2>
            <p><strong>{t('caseDetail.overview.desc')}</strong>{caseData.description || t('caseDetail.overview.none')}</p>
            <p><strong>{t('caseDetail.overview.cavity')}</strong>{caseData.cavity_type}</p>
            <p><strong>{t('caseDetail.overview.goal')}</strong>{caseData.goal}</p>
            <p><strong>Status: </strong>{caseData.status}</p>
            <p><strong>Visibility: </strong>{caseData.visibility}</p>
            <p><strong>Project ID: </strong>{caseData.project_id || '-'}</p>
            <p><strong>Tags: </strong>{(caseData.tags || []).join(', ') || '-'}</p>
            <p><strong>Safety notes: </strong>{caseData.safety_notes || '-'}</p>
            <p><strong>Conclusions: </strong>{caseData.conclusions || '-'}</p>
          </div>
          <div className="card">
            <h2 className="card-title">{t('caseDetail.overview.paramsSymptoms')}</h2>
            {renderJson({ parameters: caseData.parameters, symptoms: caseData.symptoms, measurements: caseData.measurements })}
          </div>
        </div>
      )}

      {activeTab === 'plan' && renderGenerated('plan')}
      {activeTab === 'troubleshooting' && renderGenerated('troubleshooting')}
      {activeTab === 'rezonator' && renderGenerated('rezonator')}
      {activeTab === 'report' && renderGenerated('report')}

      {activeTab === 'knowledge' && (
        <div>
          <form className="card search-panel" onSubmit={handleSearch}>
            <h2 className="card-title">{t('caseDetail.knowledge.searchTitle')}</h2>
            <div className="input-row">
              <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder={t('caseDetail.knowledge.searchPlaceholder')} />
              <button className="btn btn-primary" type="submit">{t('common.search')}</button>
            </div>
          </form>

          <div className="card">
            <h2 className="card-title">{t('caseDetail.knowledge.sourcesTitle')}</h2>
            {sources.length === 0 ? <p>{t('caseDetail.knowledge.noSources')}</p> : sources.map((source) => (
              <div key={source.id} className="source-row">
                <strong>{source.title}</strong>
                <span className="meta-pill">{source.source_type}</span>
                <span className="meta-pill">{source.governance_status}</span>
                <span className="meta-pill">v{source.version}</span>
              </div>
            ))}
          </div>

          {searchResults.length > 0 && (
            <div className="card">
              <h2 className="card-title">{t('caseDetail.knowledge.resultsTitle')}</h2>
              {searchResults.map((result) => (
                <article key={result.chunk_id} className="generated-card">
                  <div className="generated-card-title">
                    <span>{result.title}</span>
                    <span className="meta-pill">#{result.rank} · {result.score}</span>
                  </div>
                  <p>{result.snippet}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'agent' && (
        <div>
          <form className="card" onSubmit={handleAgentSubmit}>
            <h2 className="card-title">{t('caseDetail.agentTab.newTask')}</h2>
            <textarea value={agentGoal} onChange={(event) => setAgentGoal(event.target.value)} placeholder={t('caseDetail.agentTab.placeholder')} rows={4} />
            <div className="input-row">
              <select value={agentMode} onChange={(event) => setAgentMode(event.target.value)}>
                <option value="troubleshooting">{t('caseDetail.agentTab.mTroubleshooting')}</option>
                <option value="plan">{t('caseDetail.agentTab.mPlan')}</option>
                <option value="report">{t('caseDetail.agentTab.mReport')}</option>
                <option value="rezonator">{t('caseDetail.agentTab.mRezonator')}</option>
              </select>
              <button className="btn btn-primary" disabled={agentRunning} type="submit">
                {agentRunning ? t('caseDetail.agentTab.running') : t('caseDetail.agentTab.run')}
              </button>
            </div>
          </form>

          {tasks.map((task) => (
            <article key={task.id} className="card">
              <div className="generated-card-title">
                <h2 className="card-title">{t('caseDetail.agentTab.taskTitle')}{task.id}</h2>
                <span className="meta-pill">{task.status} · {task.risk_level}</span>
              </div>
              <p>{task.goal}</p>
              <div className="timeline">
                {task.steps.map((step) => (
                  <div key={step.id} className="timeline-step">
                    <span className="step-index">{step.step_index}</span>
                    <div>
                      <strong>{step.title}</strong>
                      <p>{step.result_summary || step.rationale}</p>
                    </div>
                  </div>
                ))}
              </div>
              <h3>{t('caseDetail.agentTab.toolCalls')}</h3>
              {task.tool_calls.map((call) => (
                <div key={call.id} className="source-row">
                  <strong>{call.tool_name}</strong>
                  <span className="meta-pill">{call.status}</span>
                </div>
              ))}
            </article>
          ))}
        </div>
      )}

      {activeTab === 'attachments' && (
        <div>
          <div className="card">
            <h2 className="card-title">{t('caseDetail.attachmentsTab.uploadTitle')}</h2>
            <input type="file" onChange={handleFileUpload} />
            <p className="muted">{t('caseDetail.attachmentsTab.formats')}</p>
          </div>
          {attachments.map((attachment) => (
            <div key={attachment.id} className="card attachment-row">
              <div>
                <strong>{attachment.filename}</strong>
                <p className="muted">{attachment.file_type || t('caseDetail.attachmentsTab.unknownType')} · {new Date(attachment.uploaded_at).toLocaleString()}</p>
              </div>
              <div className="action-row">
                {isImageAttachment(attachment) && (
                  <button
                    className="btn btn-primary"
                    disabled={analyzingAttachment === attachment.id}
                    onClick={() => handleAnalyzeAttachment(attachment.id)}
                  >
                    {analyzingAttachment === attachment.id ? t('caseDetail.attachmentsTab.analyzing') : t('caseDetail.attachmentsTab.analyzeImage')}
                  </button>
                )}
                <a href={`${API_BASE_URL}/api/attachments/${attachment.id}`} className="btn btn-secondary" target="_blank" rel="noreferrer">{t('common.download')}</a>
                <button className="btn btn-danger" onClick={async () => { await casesApi.deleteAttachment(attachment.id); await loadData(); }}>{t('common.delete')}</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CaseDetail;
