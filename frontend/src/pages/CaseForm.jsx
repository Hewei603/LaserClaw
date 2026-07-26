import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { casesApi } from '../api/cases';
import { useLanguage } from '../LanguageContext';

// Keys the deterministic physics kernel reads from case.parameters
// (backend/app/physics/case_context.py). The structured fields below write
// exactly these names with the right types, so a user who knows lasers but
// not JSON can still trigger the kernel.
const PHYS_EMPTY = {
  wavelength_nm: '', pump_nm: '', gain_medium: '', target_waist_mm: '',
  R1_mm: '', R2_mm: '', L_mm: '',
  crystal_n: '', crystal_t: '', crystal_pos: '',
  nonlinear_crystal: '', shg_pm_type: 'I',
};
const NUMERIC_PHYS = ['wavelength_nm', 'pump_nm', 'target_waist_mm', 'L_mm'];
const PHYS_PARAM_KEYS = ['wavelength_nm', 'pump_nm', 'gain_medium', 'target_waist_mm',
  'R1_mm', 'R2_mm', 'L_mm', 'crystal', 'nonlinear_crystal', 'shg_pm_type'];

/** Split stored case.parameters into structured physics fields + leftovers. */
function decomposeParameters(parameters) {
  const params = parameters || {};
  const phys = { ...PHYS_EMPTY };
  for (const key of ['wavelength_nm', 'pump_nm', 'gain_medium', 'target_waist_mm', 'R1_mm', 'R2_mm', 'L_mm']) {
    if (params[key] !== undefined && params[key] !== null) phys[key] = String(params[key]);
  }
  if (params.nonlinear_crystal) phys.nonlinear_crystal = String(params.nonlinear_crystal).toLowerCase();
  if (params.shg_pm_type) phys.shg_pm_type = String(params.shg_pm_type).toUpperCase();
  const crystal = params.crystal;
  if (crystal && typeof crystal === 'object') {
    if (crystal.n != null) phys.crystal_n = String(crystal.n);
    if (crystal.thickness_mm != null) phys.crystal_t = String(crystal.thickness_mm);
    if (crystal.position_mm != null) phys.crystal_pos = String(crystal.position_mm);
  }
  const extras = {};
  for (const [key, value] of Object.entries(params)) {
    if (!PHYS_PARAM_KEYS.includes(key)) extras[key] = value;
  }
  return { phys, extras };
}

/** Assemble kernel-ready parameters from the structured fields (typed values). */
function assemblePhysics(phys) {
  const out = {};
  const num = (v) => {
    const n = parseFloat(String(v).trim());
    return Number.isNaN(n) ? null : n;
  };
  for (const key of NUMERIC_PHYS) {
    const v = num(phys[key]);
    if (phys[key] !== '' && v !== null) out[key] = v;
  }
  if (phys.gain_medium.trim()) out.gain_medium = phys.gain_medium.trim();
  for (const key of ['R1_mm', 'R2_mm']) {
    const raw = String(phys[key]).trim();
    if (!raw) continue;
    const lower = raw.toLowerCase();
    if (['flat', '平镜', '平面', 'inf'].includes(lower)) out[key] = 'flat';
    else if (num(raw) !== null) out[key] = num(raw);
  }
  const n = num(phys.crystal_n);
  const th = num(phys.crystal_t);
  if (n !== null && th !== null) {
    out.crystal = { n, thickness_mm: th };
    const pos = num(phys.crystal_pos);
    if (pos !== null) out.crystal.position_mm = pos;
  }
  if (phys.nonlinear_crystal) {
    out.nonlinear_crystal = phys.nonlinear_crystal;
    out.shg_pm_type = phys.shg_pm_type || 'I';
  }
  return out;
}

function CaseForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t, te } = useLanguage();
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

  const [phys, setPhys] = useState({ ...PHYS_EMPTY });
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
      const { phys: loadedPhys, extras } = decomposeParameters(data.parameters);
      setPhys(loadedPhys);
      setFormData({
        ...data,
        project_id: data.project_id || '',
        tags: data.tags || [],
        parameters: extras,
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
        // Structured physics fields override any same-named free entries.
        parameters: { ...formData.parameters, ...assemblePhysics(phys) },
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
            <label className="form-label">{t('caseForm.projectId')}</label>
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
            <label className="form-label">{t('caseForm.statusLabel')}</label>
            <select name="status" value={formData.status} onChange={handleChange} className="form-select">
              {['draft', 'active', 'paused', 'completed', 'archived'].map((value) => (
                <option key={value} value={value}>{t(`caseStatus.${value}`)}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label className="form-label">{t('caseForm.visibilityLabel')}</label>
            <select name="visibility" value={formData.visibility} onChange={handleChange} className="form-select">
              {['private', 'project', 'organization'].map((value) => (
                <option key={value} value={value}>{te(value)}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.tagsLabel')}</label>
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

        <div className="form-group" style={{ border: '1px solid #3a3850', borderRadius: '8px', padding: '1rem' }}>
          <label className="form-label">{t('caseForm.physTitle')}</label>
          <p className="muted" style={{ marginBottom: '1rem' }}>{t('caseForm.physHint')}</p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '1rem' }}>
            <div>
              <label className="form-label">{t('caseForm.wavelength')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="1064"
                value={phys.wavelength_nm}
                onChange={(e) => setPhys({ ...phys, wavelength_nm: e.target.value })} />
              <p className="muted" style={{ fontSize: '0.8rem' }}>{t('caseForm.wavelengthHint')}</p>
            </div>
            <div>
              <label className="form-label">{t('caseForm.pump')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="808"
                value={phys.pump_nm}
                onChange={(e) => setPhys({ ...phys, pump_nm: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.gainMedium')}</label>
              <input type="text" className="form-input" placeholder={t('caseForm.gainMediumPh')}
                value={phys.gain_medium}
                onChange={(e) => setPhys({ ...phys, gain_medium: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.targetWaist')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="0.25"
                value={phys.target_waist_mm}
                onChange={(e) => setPhys({ ...phys, target_waist_mm: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.r1')}</label>
              <input type="text" className="form-input" placeholder="flat / 500"
                value={phys.R1_mm}
                onChange={(e) => setPhys({ ...phys, R1_mm: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.r2')}</label>
              <input type="text" className="form-input" placeholder="flat / 500"
                value={phys.R2_mm}
                onChange={(e) => setPhys({ ...phys, R2_mm: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.lMm')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder=""
                value={phys.L_mm}
                onChange={(e) => setPhys({ ...phys, L_mm: e.target.value })} />
              <p className="muted" style={{ fontSize: '0.8rem' }}>{t('caseForm.lHint')}</p>
            </div>
            <div>
              <label className="form-label">{t('caseForm.nlc')}</label>
              <select className="form-select" value={phys.nonlinear_crystal}
                onChange={(e) => setPhys({ ...phys, nonlinear_crystal: e.target.value })}>
                <option value="">{t('caseForm.nlcNone')}</option>
                <option value="lbo">LBO</option>
                <option value="bbo">BBO</option>
                <option value="ktp">KTP</option>
                <option value="bibo">BiBO</option>
              </select>
            </div>
            {phys.nonlinear_crystal && (
              <div>
                <label className="form-label">{t('caseForm.pmType')}</label>
                <select className="form-select" value={phys.shg_pm_type}
                  onChange={(e) => setPhys({ ...phys, shg_pm_type: e.target.value })}>
                  <option value="I">Type I</option>
                  <option value="II">Type II</option>
                </select>
              </div>
            )}
          </div>
          <p className="muted" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>{t('caseForm.mirrorsHint')}</p>
          <label className="form-label" style={{ marginTop: '0.75rem' }}>{t('caseForm.crystalGroup')}</label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
            <div>
              <label className="form-label">{t('caseForm.crystalN')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="1.8147"
                value={phys.crystal_n}
                onChange={(e) => setPhys({ ...phys, crystal_n: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.crystalT')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="10"
                value={phys.crystal_t}
                onChange={(e) => setPhys({ ...phys, crystal_t: e.target.value })} />
            </div>
            <div>
              <label className="form-label">{t('caseForm.crystalPos')}</label>
              <input type="text" inputMode="decimal" className="form-input" placeholder="20"
                value={phys.crystal_pos}
                onChange={(e) => setPhys({ ...phys, crystal_pos: e.target.value })} />
            </div>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.paramsLabel')}</label>
          <p className="muted">{t('caseForm.paramsHint')}</p>
          <div style={{ marginBottom: '1rem' }}>
            {Object.entries(formData.parameters).map(([key, value]) => (
              <div key={key} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>
                  {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
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
          <label className="form-label">{t('caseForm.measurementsLabel')}</label>
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
            <input type="text" placeholder={t('caseForm.measurementName')} value={measurementKey} onChange={(e) => setMeasurementKey(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <input type="text" placeholder={t('caseForm.measurementValue')} value={measurementValue} onChange={(e) => setMeasurementValue(e.target.value)} className="form-input" style={{ flex: 1 }} />
            <button type="button" onClick={addMeasurement} className="btn btn-secondary">{t('common.add')}</button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.safetyNotesLabel')}</label>
          <textarea name="safety_notes" value={formData.safety_notes || ''} onChange={handleChange} className="form-textarea" />
        </div>

        <div className="form-group">
          <label className="form-label">{t('caseForm.conclusionsLabel')}</label>
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
