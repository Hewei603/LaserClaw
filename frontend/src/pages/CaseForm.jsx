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
    status: 'draft',
    visibility: 'project',
    project_id: '',
    tags: [],
    parameters: {},
    symptoms: [],
    measurements: {},
    safety_notes: '',
    conclusions: ''
  });

  const [tagInput, setTagInput] = useState('');
  const [paramKey, setParamKey] = useState('');
  const [paramValue, setParamValue] = useState('');
  const [measurementKey, setMeasurementKey] = useState('');
  const [measurementValue, setMeasurementValue] = useState('');
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
      setFormData({
        ...data,
        project_id: data.project_id || '',
        tags: data.tags || [],
        parameters: data.parameters || {},
        symptoms: data.symptoms || [],
        measurements: data.measurements || {},
        safety_notes: data.safety_notes || '',
        conclusions: data.conclusions || '',
      });
    } catch (err) {
      setError(t('caseForm.loadFailed') + err.message);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const payload = {
        ...formData,
        project_id: formData.project_id === '' ? null : Number(formData.project_id),
      };
      if (isEdit) {
        await casesApi.update(id, payload);
        navigate(`/cases/${id}`);
      } else {
        const created = await casesApi.create(payload);
        navigate(`/cases/${created.id}`);
      }
    } catch (err) {
      setError(t('caseForm.saveFailed') + err.message);
    } finally {
      setLoading(false);
    }
  };

  const addTag = () => {
    const tag = tagInput.trim();
    if (tag && !formData.tags.includes(tag)) {
      setFormData(prev => ({ ...prev, tags: [...prev.tags, tag] }));
      setTagInput('');
    }
  };

  const removeTag = (tag) => {
    setFormData(prev => ({ ...prev, tags: prev.tags.filter(item => item !== tag) }));
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

  const addMeasurement = () => {
    if (measurementKey && measurementValue) {
      setFormData(prev => ({
        ...prev,
        measurements: { ...prev.measurements, [measurementKey]: measurementValue }
      }));
      setMeasurementKey('');
      setMeasurementValue('');
    }
  };

  const removeMeasurement = (key) => {
    setFormData(prev => {
      const next = { ...prev.measurements };
      delete next[key];
      return { ...prev, measurements: next };
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

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
          <div className="form-group">
            <label className="form-label">Project ID</label>
            <input
              type="number"
              name="project_id"
              value={formData.project_id || ''}
              onChange={handleChange}
              className="form-input"
              min="1"
            />
          </div>
          <div className="form-group">
            <label className="form-label">Status</label>
            <select name="status" value={formData.status} onChange={handleChange} className="form-select">
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">Visibility</label>
            <select name="visibility" value={formData.visibility} onChange={handleChange} className="form-select">
              <option value="private">Private</option>
              <option value="project">Project</option>
              <option value="organization">Organization</option>
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Tags</label>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
            {(formData.tags || []).map(tag => (
              <button key={tag} type="button" className="meta-pill" onClick={() => removeTag(tag)}>{tag} x</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input value={tagInput} onChange={(e) => setTagInput(e.target.value)} className="form-input" placeholder="tag" />
            <button type="button" onClick={addTag} className="btn btn-secondary">{t('common.add')}</button>
          </div>
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

        <div className="form-group">
          <label className="form-label">Measurements</label>
          <div style={{ marginBottom: '1rem' }}>
            {Object.entries(formData.measurements || {}).map(([key, value]) => (
              <div key={key} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>
                  {key}: {value}
                </span>
                <button type="button" onClick={() => removeMeasurement(key)} className="btn btn-danger">
                  {t('common.delete')}
                </button>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input type="text" placeholder="name" value={measurementKey} onChange={(e) => setMeasurementKey(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <input type="text" placeholder="value" value={measurementValue} onChange={(e) => setMeasurementValue(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <button type="button" onClick={addMeasurement} className="btn btn-secondary">{t('common.add')}</button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">Safety notes</label>
          <textarea name="safety_notes" value={formData.safety_notes || ''} onChange={handleChange} className="form-textarea" />
        </div>

        <div className="form-group">
          <label className="form-label">Conclusions</label>
          <textarea name="conclusions" value={formData.conclusions || ''} onChange={handleChange} className="form-textarea" />
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
