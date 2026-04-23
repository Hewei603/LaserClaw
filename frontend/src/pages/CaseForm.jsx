import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { casesApi } from '../api/cases';

function CaseForm() {
  const { id } = useParams();
  const navigate = useNavigate();
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
      setError('加载案例失败: ' + err.message);
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
      setError('保存失败: ' + err.message);
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
      <h1>{isEdit ? '编辑案例' : '新建案例'}</h1>

      {error && <div className="error">{error}</div>}

      <form onSubmit={handleSubmit} style={{ marginTop: '2rem' }}>
        <div className="form-group">
          <label className="form-label">标题 *</label>
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
          <label className="form-label">描述</label>
          <textarea
            name="description"
            value={formData.description}
            onChange={handleChange}
            className="form-textarea"
          />
        </div>

        <div className="form-group">
          <label className="form-label">腔型 *</label>
          <select
            name="cavity_type"
            value={formData.cavity_type}
            onChange={handleChange}
            className="form-select"
            required
          >
            <option value="linear">线性腔</option>
            <option value="ring">环形腔</option>
            <option value="bow-tie">蝴蝶形腔</option>
            <option value="custom">自定义</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">实验目标 *</label>
          <textarea
            name="goal"
            value={formData.goal}
            onChange={handleChange}
            className="form-textarea"
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label">关键参数</label>
          <div style={{ marginBottom: '1rem' }}>
            {Object.entries(formData.parameters).map(([key, value]) => (
              <div key={key} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>
                  {key}: {value}
                </span>
                <button
                  type="button"
                  onClick={() => removeParameter(key)}
                  className="btn btn-danger"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              placeholder="参数名"
              value={paramKey}
              onChange={(e) => setParamKey(e.target.value)}
              className="form-input"
              style={{ flex: 1 }}
            />
            <input
              type="text"
              placeholder="参数值"
              value={paramValue}
              onChange={(e) => setParamValue(e.target.value)}
              className="form-input"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              onClick={addParameter}
              className="btn btn-secondary"
            >
              添加
            </button>
          </div>
        </div>

        <div className="form-group">
          <label className="form-label">观察到的症状</label>
          <div style={{ marginBottom: '1rem' }}>
            {commonSymptoms.map(symptom => (
              <label key={symptom} style={{ display: 'block', marginBottom: '0.5rem', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={formData.symptoms.includes(symptom)}
                  onChange={() => toggleSymptom(symptom)}
                  style={{ marginRight: '0.5rem' }}
                />
                {symptom}
              </label>
            ))}
          </div>
          <div>
            <p style={{ marginBottom: '0.5rem', color: '#b0b0b0' }}>自定义症状:</p>
            {formData.symptoms.filter(s => !commonSymptoms.includes(s)).map(symptom => (
              <div key={symptom} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                <span style={{ flex: 1, padding: '0.5rem', backgroundColor: '#1a1825', border: '1px solid #2a2838', borderRadius: '4px' }}>
                  {symptom}
                </span>
                <button
                  type="button"
                  onClick={() => removeSymptom(symptom)}
                  className="btn btn-danger"
                >
                  删除
                </button>
              </div>
            ))}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <input
                type="text"
                placeholder="输入自定义症状"
                value={customSymptom}
                onChange={(e) => setCustomSymptom(e.target.value)}
                className="form-input"
                style={{ flex: 1 }}
              />
              <button
                type="button"
                onClick={addCustomSymptom}
                className="btn btn-secondary"
              >
                添加
              </button>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? '保存中...' : '保存'}
          </button>
          <Link to="/cases" className="btn btn-secondary">
            取消
          </Link>
        </div>
      </form>
    </div>
  );
}

export default CaseForm;
