import React, { useEffect, useState } from 'react';
import { casesApi } from '../api/cases';
import { literatureApi } from '../api/literature';
import { LiteratureSearchResult } from '../components/ModuleResults';
import { useLanguage } from '../LanguageContext';

// Standalone literature search: look something up without creating a case
// first. "存入案例" replays the same search as a case module, so the archived
// copy went through exactly the same deterministic path as this page.
function LiteraturePage() {
  const { t } = useLanguage();
  const [form, setForm] = useState({ query: '', yearFrom: '', maxResults: '20', sort: 'relevance' });
  const [result, setResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState(null);
  const [cases, setCases] = useState([]);
  const [saveCaseId, setSaveCaseId] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedNote, setSavedNote] = useState(null);

  useEffect(() => {
    casesApi.list().then((data) => setCases(Array.isArray(data) ? data : [])).catch(() => setCases([]));
  }, []);

  const handleSearch = async (event) => {
    event.preventDefault();
    if (!form.query.trim()) {
      setError(t('literaturePage.needQuery'));
      return;
    }
    setSearching(true);
    setError(null);
    setSavedNote(null);
    try {
      setResult(await literatureApi.search({
        query: form.query.trim(),
        yearFrom: form.yearFrom.trim() || undefined,
        maxResults: form.maxResults.trim() || undefined,
        sort: form.sort,
      }));
    } catch (err) {
      setError(t('literaturePage.searchFailed') + err.message);
      setResult(null);
    } finally {
      setSearching(false);
    }
  };

  const handleSaveToCase = async () => {
    if (!saveCaseId) return;
    setSaving(true);
    setError(null);
    try {
      const config = { query: form.query.trim(), sort: form.sort };
      if (form.yearFrom.trim()) config.year_from = Number(form.yearFrom.trim());
      if (form.maxResults.trim()) config.max_results = Number(form.maxResults.trim());
      const module = await casesApi.createModule(Number(saveCaseId), {
        module_type: 'literature_search',
        config_json: config,
      });
      await casesApi.runModule(module.id, { config_json: config });
      setSavedNote(t('literaturePage.savedNote'));
    } catch (err) {
      setError(t('literaturePage.saveFailed') + err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="detail-header">
        <div>
          <h1>{t('literaturePage.title')}</h1>
          <p className="muted">{t('literaturePage.subtitle')}</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <form className="card" onSubmit={handleSearch}>
        <div className="input-row" style={{ flexWrap: 'wrap' }}>
          <label style={{ flexGrow: 1 }}>
            {t('literaturePage.query')}
            <input value={form.query} onChange={(e) => setForm({ ...form, query: e.target.value })}
              placeholder="Nd:YAG passive Q-switching" />
          </label>
          <label>
            {t('literaturePage.yearFrom')}
            <input value={form.yearFrom} onChange={(e) => setForm({ ...form, yearFrom: e.target.value })}
              placeholder="2015" />
          </label>
          <label>
            {t('literaturePage.maxResults')}
            <input value={form.maxResults} onChange={(e) => setForm({ ...form, maxResults: e.target.value })} />
          </label>
          <label>
            {t('literaturePage.sort')}
            <select value={form.sort} onChange={(e) => setForm({ ...form, sort: e.target.value })}>
              <option value="relevance">{t('literaturePage.sortRelevance')}</option>
              <option value="citations">{t('literaturePage.sortCitations')}</option>
              <option value="year">{t('literaturePage.sortYear')}</option>
            </select>
          </label>
          <button className="btn btn-primary" type="submit" disabled={searching}>
            {searching ? t('literaturePage.searching') : t('literaturePage.searchBtn')}
          </button>
        </div>
        <p className="muted">{t('literaturePage.sourcesHint')}</p>
      </form>

      {result && (
        <div className="card">
          {result.status !== 'completed' && result.message && (
            <div className={result.status === 'failed' ? 'error' : 'disclaimer'}>{result.message}</div>
          )}
          {result.status === 'completed' && (
            <>
              {cases.length > 0 && (
                <div className="action-row no-print">
                  <select value={saveCaseId} onChange={(e) => setSaveCaseId(e.target.value)}>
                    <option value="">{t('literaturePage.pickCase')}</option>
                    {cases.map((c) => <option key={c.id} value={c.id}>#{c.id} {c.title}</option>)}
                  </select>
                  <button className="btn btn-secondary" type="button"
                    disabled={!saveCaseId || saving} onClick={handleSaveToCase}>
                    {saving ? t('literaturePage.saving') : t('literaturePage.saveToCase')}
                  </button>
                  {savedNote && <span className="muted">{savedNote}</span>}
                </div>
              )}
              <LiteratureSearchResult result={result} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default LiteraturePage;
