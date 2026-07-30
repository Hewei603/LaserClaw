import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { agentApi } from '../api/agent';
import { API_BASE_URL } from '../api/client';
import { casesApi } from '../api/cases';
import { knowledgeApi } from '../api/knowledge';
import { ModuleResult, PhysicsFactsBlock } from '../components/ModuleResults';
import { useLanguage } from '../LanguageContext';

function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, te } = useLanguage();

  const tabs = [
    ['overview', t('caseDetail.tabs.overview')],
    ['plan', t('caseDetail.tabs.plan')],
    ['troubleshooting', t('caseDetail.tabs.troubleshooting')],
    ['report', t('caseDetail.tabs.report')],
    ['knowledge', t('caseDetail.tabs.knowledge')],
    ['modules', t('caseDetail.tabs.modules')],
    ['agent', t('caseDetail.tabs.agent')],
    ['attachments', t('caseDetail.tabs.attachments')],
  ];
  const caseId = Number(id);

  const [caseData, setCaseData] = useState(null);
  const [generatedContents, setGeneratedContents] = useState({});
  const [attachments, setAttachments] = useState([]);
  const [sources, setSources] = useState([]);
  const [modules, setModules] = useState([]);
  const [components, setComponents] = useState([]);
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
  const [newModuleType, setNewModuleType] = useState('stability');
  const [moduleRunning, setModuleRunning] = useState(null);
  const [moduleConfigs, setModuleConfigs] = useState({});
  const [actionError, setActionError] = useState(null);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [caseResult, contentsResult, attachmentsResult, sourcesResult, tasksResult, modulesResult, componentsResult] = await Promise.all([
        casesApi.get(id),
        casesApi.getGeneratedContents(id),
        casesApi.listAttachments(id),
        knowledgeApi.listSources(caseId),
        agentApi.listTasks(caseId),
        casesApi.listModules(id),
        casesApi.listComponents(id),
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
      setModules(modulesResult);
      setComponents(componentsResult);
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
      if (type === 'troubleshooting') await casesApi.generateTroubleshooting(id);
      if (type === 'report') await casesApi.generateReport(id);
      await loadData();
    } catch (err) {
      setActionError(t('caseDetail.attachmentsTab.generateFailed') + err.message);
    } finally {
      setGenerating((prev) => ({ ...prev, [type]: false }));
    }
  };

  const handleSearch = async (event) => {
    event.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const response = await knowledgeApi.search({ query: searchQuery, caseId, topK: 8 });
      setSearchResults(response.results);
      setHasSearched(true);
    } catch (err) {
      setActionError(t('caseDetail.actionFailed') + err.message);
    } finally {
      setSearching(false);
    }
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
      setActionError(t('caseDetail.agentTab.taskFailed') + err.message);
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
      setActionError(t('caseDetail.attachmentsTab.uploadFailed') + err.message);
    }
  };

  const handleAnalyzeAttachment = async (attachmentId) => {
    setAnalyzingAttachment(attachmentId);
    try {
      await casesApi.analyzeAttachment(attachmentId);
      await loadData();
      setActiveTab('attachments');
    } catch (err) {
      setActionError(t('caseDetail.attachmentsTab.uploadFailed') + err.message);
    } finally {
      setAnalyzingAttachment(null);
    }
  };

  const handleCreateModule = async () => {
    try {
      await casesApi.createModule(id, { module_type: newModuleType });
      await loadData();
      setActiveTab('modules');
    } catch (err) {
      setActionError(t('caseDetail.actionFailed') + err.message);
    }
  };

  const handleModuleUpload = async (moduleId, event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      await casesApi.uploadModuleFile(moduleId, file);
      event.target.value = '';
      await loadData();
    } catch (err) {
      setActionError(t('caseDetail.modulesTab.uploadFailed') + err.message);
    }
  };

  const handleRunModule = async (module) => {
    let config = {};
    const text = (moduleConfigs[module.id] || '').trim();
    if (text) {
      try {
        config = JSON.parse(text);
      } catch {
        setActionError(t('caseDetail.modulesTab.badConfig'));
        return;
      }
    }
    setModuleRunning(module.id);
    try {
      await casesApi.runModule(module.id, { config_json: config });
      await loadData();
    } catch (err) {
      setActionError(t('caseDetail.modulesTab.runFailed') + err.message);
    } finally {
      setModuleRunning(null);
    }
  };

  const handleToggleOwned = async (item) => {
    try {
      await casesApi.updateComponent(item.id, { owned: !item.owned });
      await loadData();
    } catch (err) {
      setActionError(t('caseDetail.actionFailed') + err.message);
    }
  };

  const isImageAttachment = (attachment) => {
    const type = attachment.file_type || '';
    const name = attachment.filename || '';
    return type.startsWith('image/') || /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(name);
  };

  const handleDelete = async () => {
    if (!window.confirm(t('caseDetail.confirmDelete'))) return;
    try {
      await casesApi.delete(id);
      navigate('/cases');
    } catch (err) {
      setActionError(t('caseDetail.actionFailed') + err.message);
    }
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

  const moduleLabel = (type) => {
    const labels = {
      stability: t('caseDetail.modulesTab.stability'),
      beam_profile: t('caseDetail.modulesTab.beamProfile'),
      spectrum: t('caseDetail.modulesTab.spectrum'),
      components: t('caseDetail.modulesTab.components'),
      cavity_design: t('caseDetail.modulesTab.cavityDesign'),
      phase_match: t('caseDetail.modulesTab.phaseMatch'),
      coating_tmm: t('caseDetail.modulesTab.coatingTmm'),
      component_match: t('caseDetail.modulesTab.componentMatch'),
      power_curve: t('caseDetail.modulesTab.powerCurve'),
    };
    return labels[type] || type;
  };

  const latestPowerCurveId = Math.max(
    -1, ...modules.filter((m) => m.module_type === 'power_curve').map((m) => m.id),
  );

  const renderModules = () => (
    <div>
      <div className="card">
        <h2 className="card-title">{t('caseDetail.modulesTab.addTitle')}</h2>
        <div className="input-row">
          <select value={newModuleType} onChange={(event) => setNewModuleType(event.target.value)}>
            <optgroup label={t('caseDetail.modulesTab.groupMeasure')}>
              <option value="power_curve">{t('caseDetail.modulesTab.powerCurve')}</option>
              <option value="stability">{t('caseDetail.modulesTab.stability')}</option>
              <option value="beam_profile">{t('caseDetail.modulesTab.beamProfile')}</option>
              <option value="spectrum">{t('caseDetail.modulesTab.spectrum')}</option>
            </optgroup>
            <optgroup label={t('caseDetail.modulesTab.groupCompute')}>
              <option value="cavity_design">{t('caseDetail.modulesTab.cavityDesign')}</option>
              <option value="phase_match">{t('caseDetail.modulesTab.phaseMatch')}</option>
              <option value="coating_tmm">{t('caseDetail.modulesTab.coatingTmm')}</option>
              <option value="component_match">{t('caseDetail.modulesTab.componentMatch')}</option>
            </optgroup>
            <optgroup label="—">
              <option value="components">{t('caseDetail.modulesTab.components')}</option>
            </optgroup>
          </select>
          <button className="btn btn-primary" onClick={handleCreateModule}>{t('common.add')}</button>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">{t('caseDetail.modulesTab.runConfig')}</h2>
        <p className="muted">{t('caseDetail.modulesTab.configHint')}</p>
        <details>
          <summary className="muted">{t('caseDetail.modulesTab.configExamples')}</summary>
          <p className="muted mono">{t('caseDetail.modulesTab.exCavity')}</p>
          <p className="muted mono">{t('caseDetail.modulesTab.exPhase')}</p>
          <p className="muted mono">{t('caseDetail.modulesTab.exCoating')}</p>
          <p className="muted mono">{t('caseDetail.modulesTab.exPower')}</p>
        </details>
      </div>

      {modules.length === 0 && <div className="card"><p>{t('caseDetail.modulesTab.empty')}</p></div>}
      {modules.map((module) => (
        <article key={module.id} className="card">
          <div className="generated-card-title">
            <div>
              <h2 className="card-title">{module.title}</h2>
              <span className="meta-pill">{moduleLabel(module.module_type)}</span>
              <span className={`meta-pill status-${module.status}`}>{te(module.status)}</span>
            </div>
            <div className="action-row">
              <input type="file" onChange={(event) => handleModuleUpload(module.id, event)} />
              <button className="btn btn-primary" disabled={moduleRunning === module.id} onClick={() => handleRunModule(module)}>
                {moduleRunning === module.id ? t('caseDetail.modulesTab.running') : t('caseDetail.modulesTab.run')}
              </button>
            </div>
          </div>
          <textarea
            className="module-config"
            value={moduleConfigs[module.id] || ''}
            onChange={(event) => setModuleConfigs((prev) => ({ ...prev, [module.id]: event.target.value }))}
            rows={2}
            placeholder={t('caseDetail.modulesTab.runConfig')}
          />

          {module.files.length > 0 && (
            <div className="generated-section">
              <h3>{t('caseDetail.modulesTab.files')}</h3>
              {module.files.map((file) => (
                <div key={file.id} className="source-row">
                  <span>{file.filename}</span>
                  <div className="action-row">
                    <span className="meta-pill">{file.file_role}</span>
                    <a className="btn btn-secondary" href={casesApi.moduleFileUrl(file.id)} target="_blank" rel="noreferrer">{t('common.download')}</a>
                  </div>
                </div>
              ))}
            </div>
          )}

          {module.module_type === 'components' && (
            <div className="generated-section">
              <div className="generated-card-title">
                <h3>{t('caseDetail.modulesTab.componentList')}</h3>
                <a className="btn btn-secondary" href={casesApi.procurementUrl(id)} target="_blank" rel="noreferrer">{t('caseDetail.modulesTab.exportProcurement')}</a>
              </div>
              {components.length === 0 ? <p>{t('caseDetail.modulesTab.noComponents')}</p> : components.map((item) => (
                <div key={item.id} className="source-row">
                  <div>
                    <strong>{item.name}</strong>
                    <p className="muted">{item.category} · {item.specification || '-'} · {item.quantity} {item.unit}</p>
                  </div>
                  <div className="action-row">
                    <span className="meta-pill">{item.procurement_status}</span>
                    <button className="btn btn-secondary" onClick={() => handleToggleOwned(item)}>
                      {item.owned ? t('caseDetail.modulesTab.owned') : t('caseDetail.modulesTab.markOwned')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <ModuleResult moduleType={module.module_type} result={module.result_json}
            showComparison={module.id === latestPowerCurveId} />
          {module.result_json && Object.keys(module.result_json).length > 0 && (
            <details>
              <summary className="muted">{t('caseDetail.modulesTab.rawResult')}</summary>
              {renderJson(module.result_json)}
            </details>
          )}
        </article>
      ))}
    </div>
  );

  // Keys handled specially (or internal) — everything else renders generically,
  // so no provider's output field silently disappears from the card again.
  const HANDLED_KEYS = new Set([
    'title', 'summary', 'disclaimer', 'notice', 'citations', 'computed_physics',
    'retrieval', 'confidence', 'usage', 'model', 'model_provider', 'goal',
  ]);

  const sectionTitle = (key) => {
    const translated = t(`caseDetail.genSections.${key}`);
    return translated !== `caseDetail.genSections.${key}` ? translated : key.replace(/_/g, ' ');
  };

  const entryLine = (entry) => {
    if (typeof entry !== 'object' || entry === null) return String(entry);
    return entry.title || entry.step_title || entry.description || entry.step || entry.name
      || entry.symptom || entry.check || entry.action || JSON.stringify(entry);
  };

  const renderValue = (key, value) => {
    if (value == null || value === '') return null;
    if (Array.isArray(value)) {
      if (value.length === 0) return null;
      return (
        <div key={key} className="generated-section">
          <h3>{sectionTitle(key)}</h3>
          <ol>
            {value.map((entry, i) => (
              <li key={i}>{entryLine(entry)}
                {typeof entry === 'object' && entry !== null && (entry.detail || (entry.description && entry.title)) && (
                  <p className="muted">{entry.detail || entry.description}</p>
                )}
                {typeof entry === 'object' && entry !== null && Array.isArray(entry.possible_causes) && (
                  <ul>
                    {entry.possible_causes.map((cause, j) => <li key={j} className="muted">{cause}</li>)}
                  </ul>
                )}
                {typeof entry === 'object' && entry !== null && Array.isArray(entry.solutions || entry.recommended_actions) && (
                  <ul>
                    {(entry.solutions || entry.recommended_actions).map((s, j) => <li key={j}>{s}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        </div>
      );
    }
    if (typeof value === 'object') {
      return (
        <div key={key} className="generated-section">
          <h3>{sectionTitle(key)}</h3>
          <table className="mini-table">
            <tbody>
              {Object.entries(value).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td className="num">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <div key={key} className="generated-section">
        <h3>{sectionTitle(key)}</h3>
        <p>{String(value)}</p>
      </div>
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
          {generating[type] && <p className="muted">{t('caseDetail.generatingHint')}</p>}
        </div>
      );
    }
    const c = item.content || {};
    return (
      <div className="card">
        <div className="generated-card-title">
          <h2 className="card-title">{c.title || c.summary || item.content_type}</h2>
          <div className="action-row">
            {item.model && <span className="meta-pill">{t('caseDetail.modelLabel')}: {item.model}</span>}
            {item.latency_ms != null && <span className="meta-pill">{t('caseDetail.latencyLabel')}: {(item.latency_ms / 1000).toFixed(1)}s</span>}
            {/* Print lives with the content, not in the page header: only the
                active tab is mounted, so a header button would print whatever
                tab happens to be open rather than what the user is looking at. */}
            <button className="btn btn-secondary" onClick={() => window.print()}
              title={t('caseDetail.printHint')}>
              {t('caseDetail.print')}
            </button>
            <button className="btn btn-secondary" disabled={generating[type]} onClick={() => handleGenerate(type)}>
              {generating[type] ? t('caseDetail.generating') : t('caseDetail.generate')}
            </button>
          </div>
        </div>
        {generating[type] && <p className="muted">{t('caseDetail.generatingHint')}</p>}
        {c.notice && <div className="disclaimer">{c.notice}</div>}
        {type === 'plan' && <PhysicsFactsBlock physics={c.computed_physics} />}
        {c.summary && c.title && <p className="result-summary">{c.summary}</p>}
        {Object.entries(c).filter(([key]) => !HANDLED_KEYS.has(key)).map(([key, value]) => renderValue(key, value))}
        {c.disclaimer && <div className="disclaimer">{c.disclaimer}</div>}
        {renderCitations(c.citations)}
        <details>
          <summary className="muted">{t('caseDetail.modulesTab.rawResult')}</summary>
          {renderJson(c)}
        </details>
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
          <a href={casesApi.bundleUrl(id)} className="btn btn-secondary" target="_blank" rel="noreferrer">{t('caseDetail.exportBundle')}</a>
          <Link to={`/cases/${id}/edit`} className="btn btn-secondary">{t('common.edit')}</Link>
          <button onClick={handleDelete} className="btn btn-danger">{t('common.delete')}</button>
        </div>
      </div>

      {actionError && (
        <div className="error action-error">
          <span>{actionError}</span>
          <button className="btn btn-secondary" onClick={() => setActionError(null)}>{t('caseDetail.dismiss')}</button>
        </div>
      )}

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
            <p><strong>{t('caseDetail.overview.status')}</strong>{t(`caseStatus.${caseData.status}`) !== `caseStatus.${caseData.status}` ? t(`caseStatus.${caseData.status}`) : caseData.status}</p>
            <p><strong>{t('caseDetail.overview.visibility')}</strong>{te(caseData.visibility)}</p>
            <p><strong>{t('caseDetail.overview.projectId')}</strong>{caseData.project_id || '-'}</p>
            <p><strong>{t('caseDetail.overview.tags')}</strong>{(caseData.tags || []).join(', ') || '-'}</p>
            <p><strong>{t('caseDetail.overview.safetyNotes')}</strong>{caseData.safety_notes || '-'}</p>
            <p><strong>{t('caseDetail.overview.conclusions')}</strong>{caseData.conclusions || '-'}</p>
          </div>
          <div className="card">
            <h2 className="card-title">{t('caseDetail.overview.paramsSymptoms')}</h2>
            <h3>{t('caseDetail.overview.parameters')}</h3>
            {Object.keys(caseData.parameters || {}).length === 0 ? <p className="muted">-</p> : (
              <table className="mini-table">
                <tbody>
                  {Object.entries(caseData.parameters).map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td className="num">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            <h3>{t('caseDetail.overview.symptoms')}</h3>
            <div className="stat-row">
              {(caseData.symptoms || []).length === 0 ? <p className="muted">-</p>
                : caseData.symptoms.map((sym) => <span key={sym} className="meta-pill">{sym}</span>)}
            </div>
            {Object.keys(caseData.measurements || {}).length > 0 && (
              <details><summary className="muted">{t('caseDetail.overview.measurements')}</summary>{renderJson(caseData.measurements)}</details>
            )}
          </div>
        </div>
      )}

      {activeTab === 'plan' && renderGenerated('plan')}
      {activeTab === 'troubleshooting' && renderGenerated('troubleshooting')}
      {activeTab === 'report' && renderGenerated('report')}

      {activeTab === 'knowledge' && (
        <div>
          <form className="card search-panel" onSubmit={handleSearch}>
            <h2 className="card-title">{t('caseDetail.knowledge.searchTitle')}</h2>
            <div className="input-row">
              <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder={t('caseDetail.knowledge.searchPlaceholder')} />
              <button className="btn btn-primary" type="submit" disabled={searching}>{searching ? t('caseDetail.knowledge.searching') : t('common.search')}</button>
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

          {hasSearched && searchResults.length === 0 && (
            <div className="card"><p className="muted">{t('caseDetail.knowledge.noResults')}</p></div>
          )}
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

      {activeTab === 'modules' && renderModules()}

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
                <option value="cavity_design">{t('caseDetail.agentTab.mCavityDesign')}</option>
                <option value="phase_match">{t('caseDetail.agentTab.mPhaseMatch')}</option>
                <option value="coating_tmm">{t('caseDetail.agentTab.mCoatingTmm')}</option>
                <option value="component_match">{t('caseDetail.agentTab.mComponentMatch')}</option>
                <option value="power_curve">{t('caseDetail.agentTab.mPowerCurve')}</option>
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
                <span className={`meta-pill status-${task.status}`}>{te(task.status)} · {task.risk_level}</span>
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
                  <div className="action-row">
                    <span className="meta-pill">{call.status}</span>
                    {call.latency_ms != null && <span className="meta-pill">{call.latency_ms} ms</span>}
                  </div>
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
