import React, { useEffect, useState } from 'react';
import { getAgentSettings, saveAgentSettings, getCodexStatus, testCodexConnection } from '../api/settings';
import { useLanguage } from '../LanguageContext';

export default function AgentSettings() {
  const { t } = useLanguage();
  const [config, setConfig] = useState(null);
  const [provider, setProvider] = useState('mock');
  const [apiProvider, setApiProvider] = useState('openai');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [reload, setReload] = useState(0);
  const [codexPath, setCodexPath] = useState('');
  const [timeout, setTimeoutValue] = useState(300);
  const [reasoning, setReasoning] = useState('medium');
  const [checking, setChecking] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState('');

  const selectProvider = (data, name) => {
    const option = data.providers.find((item) => item.id === name);
    setProvider(option ? name : 'mock');
    if (name !== 'codex_exec') setApiProvider(option ? name : 'openai');
    setModel(option?.model || '');
    setBaseUrl(option?.base_url || '');
    setApiKey('');
    setShowKey(false);
    setSaved(false);
    setError('');
    setTestResult('');
    setCodexPath(data.codex_exec?.configured_path || '');
    setTimeoutValue(data.codex_exec?.timeout_seconds || 300);
    setReasoning(data.codex_exec?.reasoning_effort || 'medium');
  };

  useEffect(() => {
    let active = true;
    getAgentSettings().then((data) => {
      if (!active) return;
      setConfig(data);
      selectProvider(data, data.provider);
    }).catch((err) => {
      if (active) setError(err.message);
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [reload]);

  const option = config?.providers.find((item) => item.id === provider);
  const current = config?.providers.find((item) => item.id === config.provider);
  const demo = config?.status.is_mock;
  const codex = provider === 'codex_exec';
  const busy = saving || testing || checking;
  const edit = (setter) => (event) => {
    setter(event.target.value);
    setSaved(false);
    setError('');
    setTestResult('');
  };

  const payload = () => ({
    provider, model: model.trim(),
    ...(codex ? {
      executable_path: codexPath.trim(), timeout_seconds: Number(timeout), reasoning_effort: reasoning,
    } : {
      ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      ...(option?.base_url !== null && baseUrl.trim() ? { base_url: baseUrl.trim() } : {}),
    }),
  });

  const refreshCodex = async () => {
    setChecking(true); setError(''); setTestResult('');
    try {
      const runtime = await getCodexStatus(codexPath.trim());
      setConfig((previous) => ({
        ...previous, codex_exec: { ...previous.codex_exec, ...runtime },
        status: previous.provider === 'codex_exec' ? {
          ...previous.status, effective_provider: runtime.ready ? 'codex_exec' : null,
          error: runtime.ready ? undefined : runtime.message,
        } : previous.status,
      }));
    } catch (err) { setError(err.message); }
    finally { setChecking(false); }
  };

  const testCodex = async () => {
    if (!model.trim()) { setError(t('agentSettings.modelRequired')); return; }
    setTesting(true); setError(''); setTestResult('');
    try {
      const result = await testCodexConnection(payload());
      setTestResult(t('agentSettings.testSucceeded') + ' · ' + result.model);
    } catch (err) { setError(err.message); }
    finally { setTesting(false); }
  };

  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setSaved(false);
    setError('');
    try {
      const data = await saveAgentSettings(payload());
      setConfig(data);
      selectProvider(data, data.provider);
      setSaved(true);
      window.dispatchEvent(new CustomEvent('agent-settings-updated', { detail: data.status }));
    } catch (err) {
      setError(err.message);
      setShowKey(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="agent-settings" aria-labelledby="agent-settings-title">
      <div className="agent-settings-heading">
        <div>
          <div className="agent-settings-eyebrow">AGENT SETTINGS</div>
          <h2 id="agent-settings-title">{t('agentSettings.title')}</h2>
          <p className="agent-settings-hint">{t('agentSettings.description')}</p>
        </div>
        {config && (
          <span className={`agent-settings-status${demo || config.status.error ? ' is-demo' : ''}`}>
            {demo ? t('agentSettings.demo') : config.status.error ? t('agentSettings.unavailable') : t('agentSettings.configured')}
          </span>
        )}
      </div>

      {loading && <p role="status">{t('common.loading')}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !config && (
        <button className="btn btn-secondary" type="button" onClick={() => {
          setLoading(true); setError(''); setReload((value) => value + 1);
        }}>{t('agentSettings.retry')}</button>
      )}

      {config && (
        <form onSubmit={submit}>
          <fieldset className="agent-settings-fields" disabled={busy}>
            <div className="agent-settings-grid">
              <div>
                <label className="form-label" htmlFor="agent-connection">{t('agentSettings.connection')}</label>
                <select id="agent-connection" className="form-select" value={codex ? 'codex_exec' : 'api_key'}
                  onChange={(event) => selectProvider(config, event.target.value === 'codex_exec' ? 'codex_exec' : apiProvider)}>
                  <option value="api_key">API Key</option>
                  <option value="codex_exec">{t('agentSettings.codexOption')}</option>
                </select>
              </div>
              {!codex && <div>
                <label className="form-label" htmlFor="agent-provider">{t('agentSettings.provider')}</label>
                <select id="agent-provider" className="form-select" value={provider}
                  onChange={(event) => selectProvider(config, event.target.value)}>
                  {config.providers.filter((item) => item.id !== 'codex_exec').map((item) => (
                    <option key={item.id} value={item.id}>{item.id === 'mock' ? t('agentSettings.mockOption') : item.label}</option>
                  ))}
                </select>
              </div>}
              {provider !== 'mock' && (
                <div>
                  <label className="form-label" htmlFor="agent-model">{t('agentSettings.model')}</label>
                  <input id="agent-model" className="form-input" list="agent-model-options" value={model}
                    onChange={edit(setModel)} required maxLength={200} autoComplete="off"
                    aria-describedby="agent-model-hint" />
                  <datalist id="agent-model-options">
                    {option?.models.map((name) => <option key={name} value={name} />)}
                  </datalist>
                  <p className="agent-settings-hint" id="agent-model-hint">{t(codex ? 'agentSettings.codexModelHint' : 'agentSettings.modelHint')}</p>
                </div>
              )}
            </div>

            {codex ? (
              <div className="agent-settings-cli">
                <p className="agent-settings-hint">{t('agentSettings.codexHint')}</p>
                <p className="agent-settings-hint" role="status">
                  {config.codex_exec?.ready ? t('agentSettings.codexReady') : t('agentSettings.codexNotReady')}
                  {config.codex_exec?.version ? ' · ' + config.codex_exec.version : ''}
                </p>
                {!config.codex_exec?.ready && <p className="agent-settings-hint">{config.codex_exec?.message}</p>}
                <p className="agent-settings-hint">{t('agentSettings.codexLogin')} <code>codex login</code></p>
                <p className="agent-settings-hint">{t('agentSettings.codexQuota')}</p>
                <details className="agent-settings-advanced">
                  <summary>{t('agentSettings.codexAdvanced')}</summary>
                  <label className="form-label" htmlFor="agent-codex-path">{t('agentSettings.codexPath')}</label>
                  <input id="agent-codex-path" className="form-input" value={codexPath} onChange={edit(setCodexPath)}
                    placeholder={t('agentSettings.codexPathHint')} maxLength={2048} autoComplete="off" />
                  {config.codex_exec?.executable && <p className="agent-settings-hint">{config.codex_exec.executable}</p>}
                  <div className="agent-settings-grid">
                    <div>
                      <label className="form-label" htmlFor="agent-codex-timeout">{t('agentSettings.codexTimeout')}</label>
                      <input id="agent-codex-timeout" className="form-input" type="number" min={30} max={1800}
                        step={1} required value={timeout} onChange={edit(setTimeoutValue)} />
                    </div>
                    <div>
                      <label className="form-label" htmlFor="agent-codex-reasoning">{t('agentSettings.codexReasoning')}</label>
                      <select id="agent-codex-reasoning" className="form-select" value={reasoning} onChange={edit(setReasoning)}>
                        {['low', 'medium', 'high', 'xhigh', 'max', 'ultra'].map((value) => <option key={value} value={value}>{value}</option>)}
                      </select>
                    </div>
                  </div>
                </details>
                <div className="agent-settings-actions">
                  <button className="btn btn-secondary" type="button" onClick={refreshCodex}>
                    {checking ? t('common.loading') : t('agentSettings.codexRefresh')}
                  </button>
                  <button className="btn btn-secondary" type="button" onClick={testCodex}>
                    {testing ? t('agentSettings.testing') : t('agentSettings.testConnection')}
                  </button>
                </div>
                {testResult && <p className="agent-settings-success" role="status">{testResult}</p>}
              </div>
            ) : provider === 'mock' ? (
              <p className="agent-settings-hint">{t('agentSettings.mockHint')}</p>
            ) : (
              <>
                <div>
                  <label className="form-label" htmlFor="agent-api-key">API Key</label>
                  <div className="agent-settings-key">
                    <input id="agent-api-key" className="form-input" type={showKey ? 'text' : 'password'}
                      value={apiKey} onChange={edit(setApiKey)} autoComplete="new-password" spellCheck={false}
                      maxLength={8192} required={!option?.api_key_configured}
                      placeholder={t(option?.api_key_configured ? 'agentSettings.keySaved' : 'agentSettings.keyPlaceholder')}
                      aria-describedby="agent-key-hint" />
                    <button className="btn btn-secondary" type="button" aria-controls="agent-api-key"
                      aria-pressed={showKey} onClick={() => setShowKey((visible) => !visible)}>
                      {t(showKey ? 'agentSettings.hide' : 'agentSettings.show')}
                    </button>
                  </div>
                  <p className="agent-settings-hint" id="agent-key-hint">{t('agentSettings.keyHint')}</p>
                </div>
                {option?.base_url !== null && (
                  <details className="agent-settings-advanced">
                    <summary>{t('agentSettings.advanced')}</summary>
                    <label className="form-label" htmlFor="agent-base-url">Base URL</label>
                    <input id="agent-base-url" className="form-input" type="url" value={baseUrl}
                      onChange={edit(setBaseUrl)} placeholder="https://api.example.com/v1" maxLength={2048}
                      aria-describedby="agent-base-hint" />
                    <p className="agent-settings-hint" id="agent-base-hint">{t('agentSettings.baseHint')}</p>
                  </details>
                )}
              </>
            )}

            <div className="agent-settings-actions">
              <button className="btn btn-primary home-btn" type="submit" disabled={busy}>
                {saving ? t('common.saving') : t('agentSettings.save')}
              </button>
              <span className="agent-settings-hint">{t('agentSettings.current')} {current?.label || config.provider}{current?.model ? ` · ${current.model}` : ''}</span>
            </div>
          </fieldset>
          {saved && <p className="agent-settings-success" role="status">{t(codex ? 'agentSettings.codexSaved' : 'agentSettings.saved')}</p>}
          <p className="agent-settings-footnote">{t('agentSettings.scope')}</p>
        </form>
      )}
    </section>
  );
}
