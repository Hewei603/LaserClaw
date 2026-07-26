import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { casesApi } from '../api/cases';
import { useLanguage } from '../LanguageContext';

function CasesList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const { t } = useLanguage();

  useEffect(() => { loadCases(); }, []);

  const loadCases = async () => {
    try {
      setLoading(true);
      const data = await casesApi.list();
      setCases(data);
      setError(null);
    } catch (err) {
      setError(t('casesList.loadFailed') + ': ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm(t('casesList.confirmDelete'))) return;
    try {
      await casesApi.delete(id);
      loadCases();
    } catch (err) {
      setActionError(t('casesList.deleteFailed') + ': ' + err.message);
    }
  };

  const getCavityTypeLabel = (type) => t(`cavityTypes.${type}`) || type;

  if (loading) return <div className="loading">{t('common.loading')}</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>{t('casesList.title')}</h1>
        <Link to="/cases/new" className="btn btn-primary">{t('casesList.newCase')}</Link>
      </div>
      {actionError && (
        <div className="error action-error">
          <span>{actionError}</span>
          <button className="btn btn-secondary" onClick={() => setActionError(null)}>{t('caseDetail.dismiss')}</button>
        </div>
      )}
      {cases.length === 0 ? (
        <div className="card">
          <p>{t('casesList.noCases')} <Link to="/cases/new">{t('casesList.createFirst')}</Link></p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '1rem' }}>
          {cases.map((caseItem) => (
            <div key={caseItem.id} className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div style={{ flex: 1 }}>
                  <h2 className="card-title">
                    <Link to={`/cases/${caseItem.id}`}>{caseItem.title}</Link>
                  </h2>
                  <p className="card-content" style={{ marginTop: '0.5rem' }}>
                    {caseItem.description || t('common.noDescription')}
                  </p>
                  <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', fontSize: '0.9rem', color: '#888' }}>
                    <span>{t('casesList.cavity')}: {getCavityTypeLabel(caseItem.cavity_type)}</span>
                    <span>{t('casesList.status')}: {t(`caseStatus.${caseItem.status || 'draft'}`)}</span>
                    {caseItem.project_id && <span>{t('casesList.project')}: {caseItem.project_id}</span>}
                    <span>{t('casesList.created')}: {new Date(caseItem.created_at).toLocaleDateString()}</span>
                    {caseItem.symptoms?.length > 0 && (
                      <span>{t('casesList.symptoms')}: {caseItem.symptoms.length}{t('casesList.symptomsCount')}</span>
                    )}
                  </div>
                  {caseItem.tags?.length > 0 && (
                    <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {caseItem.tags.map(tag => <span key={tag} className="meta-pill">{tag}</span>)}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginLeft: '1rem' }}>
                  <Link to={`/cases/${caseItem.id}/edit`} className="btn btn-secondary">{t('common.edit')}</Link>
                  <button onClick={() => handleDelete(caseItem.id)} className="btn btn-danger">{t('common.delete')}</button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default CasesList;
