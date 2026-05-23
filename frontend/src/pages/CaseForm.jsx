import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { casesApi } from '../api/cases';
import { useLanguage } from '../LanguageContext';

function CaseForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const isEdit = !!id;

  const [formData, setFormData] = useState({
    title: '',
    description: '',
    cavity_type: 'linear',
    goal: '',
    parameters: {},
    symptoms: []
  });

  const [paramKey, setParamKey] = useState('');
  const [paramValue, setParamValue] = useState('');
  const [customSymptom, setCustomSymptom] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const commonSymptoms = [
    '无输出',
    '输出不稳定',
    '模式跳变',
    '热效应',
    '对准漂移'
  ];

  useEffect(() => {
    if (isEdit) {
      loadCase();
    }
  }, [id]);

  const loadCase = async () => {
    try {
      const data = await casesApi.get(id);
      setFormData(data);
    } catch (err) {
      setError(t('caseForm.loadFailed') + err.message);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (isEdit) {
        await casesApi.update(id, formData);
      } else {
        await casesApi.create(formData);
      }
      navigate('/cases');
    } catch (err) {
      setError(t('caseForm.saveFailed') + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const addParameter = () => {
    if (paramKey && paramValue) {
      setFormData(prev => ({
        ...prev,
        parameters: { ...prev.parameters, [paramKey]: paramValue }
      }));
      setParamKey('');
      setParamValue('');
    }
  };

  const removeParameter = (key) => {
    setFormData(prev => {
      const newParams = { ...prev.parameters };
      delete newParams[key];
      return { ...prev, parameters: newParams };
    });
  };

  const toggleSymptom = (symptom) => {
    setFormData(prev => ({
      ...prev,
      symptoms: prev.symptoms.includes(symptom)
        ? prev.symptoms.filter(s => s !== symptom)
        : [...prev.symptoms, symptom]
    }));
  };

  const addCustomSymptom = () => {
    if (customSymptom && !formData.symptoms.includes(customSymptom)) {
      setFormData(prev => ({
        ...prev,
        symptoms: [...prev.symptoms, customSymptom]
      }));
      setCustomSymptom('');
    }
  };

  const removeSymptom = (symptom) => {
    setFormData(prev => ({
      ...prev,
      symptoms: prev.symptoms.filter(s => s !== symptom)
    }));
  };

  return (
    <div>
      <h1>{isEdit ? t('caseForm.editTitle') : t('caseForm.newTitle')}</h1>

      {error && <div className="error">{error}</div>}

      <form onSubmit={handleSubmit} style={{ marginTop: '2rem' }}>
        <div className="form-group">
          <label className="form-label">{t('caseForm.titleLabel')}</label>
          <input
            type="text"
            name="title"
            value={formData.title}
            onChange={handleChange}
            className="form-input"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.descLabel')}</label>
          <textarea
            name="description"
            value={formData.description}
            onChange={handleChange}
            className="form-textarea"
          />
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.cavityLabel')}</label>
          <select
            name="cavity_type"
            value={formData.cavity_type}
            onChange={handleChange}
            className="form-select"
            required
          >
            <option value="linear">{t('cavityTypes.linear')}</option>
            <option value="ring">{t('cavityTypes.ring')}</option>
            <option value="bow-tie">{t('cavityTypes.bow-tie')}</option>
            <option value="custom">{t('cavityTypes.custom')}</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.goalLabel')}</label>
          <textarea
            name="goal"
            value={formData.goal}
            onChange={handleChange}
            className="form-textarea"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.paramsLabel')}</label>
          <div style={{ marginBottom: '1rem' }}>
            {Object.entries(formData.parameters).map(([key, value]) => (
              <div key={key} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>
                  {key}: {value}
                </span>
                <button type="button" onClick={() => removeParameter(key)} className="btn btn-danger">
                  {t('common.delete')}
                </button>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input type="text" placeholder={t('caseForm.paramName')} value={paramKey} onChange={(e) => setParamKey(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <input type="text" placeholder={t('caseForm.paramValue')} value={paramValue} onChange={(e) => setParamValue(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <button type="button" onClick={addParameter} className="btn btn-secondary">{t('common.add')}</button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.symptomsLabel')}</label>
          <div style={{ marginBottom: '1rem' }}>
            {commonSymptoms.map(symptom => (
              <label key={symptom} style={{ display: 'block', marginBottom: '0.5rem', cursor: 'pointer' }}>
                <input type="checkbox" checked={formData.symptoms.includes(symptom)} onChange={() => toggleSymptom(symptom)} style={{ marginRight: '0.5rem' }} />
                {t(`symptoms.${symptom}`)}
              </label>
            ))}
          </div>
          <div>
            <p style={{ marginBottom: '0.5rem', color: '#b0b0b0' }}>{t('caseForm.customSymptoms')}</p>
            {formData.symptoms.filter(s => !commonSymptoms.includes(s)).map(symptom => (
              <div key={symptom} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>{symptom}</span>
                <button type="button" onClick={() => removeSymptom(symptom)} className="btn btn-danger">{t('common.delete')}</button>
              </div>
            ))}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <input type="text" placeholder={t('caseForm.customSymptomPlaceholder')} value={customSymptom} onChange={(e) => setCustomSymptom(e.target.value)} className="form-input" style={{ flex: 1 }} />
              <button type="button" onClick={addCustomSymptom} className="btn btn-secondary">{t('common.add')}</button>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? t('common.saving') : t('common.save')}
          </button>
          <Link to="/cases" className="btn btn-secondary">{t('common.cancel')}</Link>
        </div>
      </form>
    </div>
  );
}

export default CaseForm;
