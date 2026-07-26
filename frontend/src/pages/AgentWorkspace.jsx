import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { agentApi } from '../api/agent';
import { casesApi } from '../api/cases';
import { knowledgeApi } from '../api/knowledge';
import { useLanguage } from '../LanguageContext';

function AgentWorkspace() {
  const { t } = useLanguage();
  const [cases, setCases] = useState([]);
  const [caseId, setCaseId] = useState('');
  const [sessionId, setSessionId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [globalSources, setGlobalSources] = useState([]);
  const [message, setMessage] = useState('');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: null,
    },
  ]);

  useEffect(() => {
    setMessages([{ role: 'assistant', text: t('agentPage.welcomeNoCase') }]);
  }, []);

  useEffect(() => {
    casesApi.list().then(setCases).catch((err) => setError(err.message));
    loadSessions(null);
    loadGlobalSources();
  }, []);

  useEffect(() => {
    const linkedCaseId = caseId ? Number(caseId) : null;
    setSessionId(null);
    setMessages([
      {
        role: 'assistant',
        text: linkedCaseId ? t('agentPage.welcomeCase') : t('agentPage.welcomeNoCase'),
      },
    ]);
    loadSessions(linkedCaseId);
  }, [caseId]);

  const loadSessions = async (linkedCaseId) => {
    try {
      const data = await agentApi.listSessions(linkedCaseId);
      setSessions(data);
    } catch (err) {
      setError(err.message);
    }
  };

  const loadGlobalSources = async () => {
    try {
      const data = await knowledgeApi.listSources();
      setGlobalSources(data.filter((item) => !item.case_id));
    } catch (err) {
      setError(err.message);
    }
  };

  const loadSession = async (id) => {
    if (!id) {
      setSessionId(null);
      setMessages([
        {
          role: 'assistant',
          text: caseId ? t('agentPage.welcomeCase') : t('agentPage.welcomeNoCase'),
        },
      ]);
      return;
    }
    try {
      const data = await agentApi.getSession(id);
      setSessionId(data.id);
      if (data.case_id) setCaseId(String(data.case_id));
      setMessages(data.messages.map((item) => ({
        role: item.role,
        text: item.content,
        routedMode: item.metadata_json?.routed_mode && item.metadata_json.routed_mode !== 'chat' ? item.metadata_json.routed_mode : null,
        task: item.metadata_json?.task_id ? { id: item.metadata_json.task_id, status: 'completed' } : null,
        citations: item.metadata_json?.citations || [],
      })));
    } catch (err) {
      setError(err.message);
    }
  };

  const selectedCase = useMemo(
    () => cases.find((item) => String(item.id) === String(caseId)),
    [cases, caseId],
  );

  const submit = async (event) => {
    event.preventDefault();
    if (!message.trim()) return;
    const userText = message.trim();
    setMessages((prev) => [...prev, { role: 'user', text: userText }]);
    setMessage('');
    setRunning(true);
    setError(null);
    try {
      const response = await agentApi.chat({
        message: userText,
        caseId: caseId ? Number(caseId) : null,
        sessionId,
      });
      setSessionId(response.session_id);
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: response.message,
        routedMode: response.routed_mode !== 'chat' ? response.routed_mode : null,
        task: response.task ? { id: response.task.id, status: response.task.status } : null,
        citations: response.citations || [],
      }]);
      loadSessions(caseId ? Number(caseId) : null);
    } catch (err) {
      setError(err.message);
      setMessages((prev) => [...prev, { role: 'assistant', text: t('agentPage.failed') + err.message }]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="agent-shell">
      <aside className="agent-sidebar">
        <div>
          <h1>{t('agentPage.title')}</h1>
          <p className="muted">{t('agentPage.desc')}</p>
        </div>
        <label className="form-label" htmlFor="agent-case">{t('agentPage.caseContext')}</label>
        <select id="agent-case" value={caseId} onChange={(event) => setCaseId(event.target.value)}>
          <option value="">{t('agentPage.noCase')}</option>
          {cases.map((item) => (
            <option key={item.id} value={item.id}>{item.title}</option>
          ))}
        </select>
        {selectedCase && (
          <div className="agent-context">
            <strong>{selectedCase.title}</strong>
            <span className="meta-pill">{selectedCase.cavity_type}</span>
            <p>{selectedCase.goal}</p>
            <Link to={`/cases/${selectedCase.id}`} className="btn btn-secondary">{t('agentPage.openCase')}</Link>
          </div>
        )}
        <label className="form-label" htmlFor="agent-session">{t('agentPage.session')}</label>
        <select id="agent-session" value={sessionId || ''} onChange={(event) => loadSession(event.target.value)}>
          <option value="">{t('agentPage.newSession')}</option>
          {sessions.map((item) => (
            <option key={item.id} value={item.id}>{item.title || `${t('agentPage.sessionFallback')}${item.id}`}</option>
          ))}
        </select>
        <div className="agent-context">
          <strong>{t('agentPage.globalKnowledge')}</strong>
          <p className="muted">{t('agentPage.globalDesc')}</p>
          {globalSources.slice(0, 5).map((source) => (
            <span key={source.id} className="meta-pill">{source.title}</span>
          ))}
          {globalSources.length === 0 && (
            <span className="muted" style={{ fontSize: '0.82rem' }}>{t('agentPage.noLabDocs')}</span>
          )}
        </div>
      </aside>

      <section className="chat-panel">
        {error && <div className="error">{error}</div>}
        <div className="chat-stream">
          {messages.map((item, index) => (
            <article key={`${item.role}-${index}`} className={`chat-message ${item.role}`}>
              <span>{item.role === 'user' ? t('agentPage.you') : 'LaserClaw'}</span>
              <p>{item.text}</p>
              {(item.routedMode || item.task) && (
                <div className="chat-meta">
                  {item.routedMode && <span className="meta-pill">{item.routedMode}</span>}
                  {item.task && <span className="meta-pill">Task #{item.task.id} · {item.task.status}</span>}
                </div>
              )}
              {(item.citations || []).length > 0 && (
                <div className="chat-citations">
                  {item.citations.slice(0, 3).map((c) => (
                    <span key={`${c.source_id}-${c.chunk_id}`} className="meta-pill" title={c.snippet}>
                      📎 {c.title} · {c.score}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
        <form className="chat-composer" onSubmit={submit}>
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder={t('agentPage.placeholder')} rows={3} />
          <button className="btn btn-primary" disabled={running} type="submit">
            {running ? t('agentPage.running') : t('agentPage.send')}
          </button>
        </form>
      </section>
    </div>
  );
}

export default AgentWorkspace;
