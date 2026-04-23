import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { casesApi } from '../api/cases';

function CasesList() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadCases();
  }, []);

  const loadCases = async () => {
    try {
      setLoading(true);
      const data = await casesApi.list();
      setCases(data);
      setError(null);
    } catch (err) {
      setError('加载案例失败: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('确定要删除这个案例吗？')) {
      return;
    }

    try {
      await casesApi.delete(id);
      loadCases();
    } catch (err) {
      alert('删除失败: ' + err.message);
    }
  };

  const getCavityTypeLabel = (type) => {
    const labels = {
      linear: '线性腔',
      ring: '环形腔',
      'bow-tie': '蝴蝶形腔',
      custom: '自定义'
    };
    return labels[type] || type;
  };

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <h1>实验案例</h1>
        <Link to="/cases/new" className="btn btn-primary">
          新建案例
        </Link>
      </div>

      {cases.length === 0 ? (
        <div className="card">
          <p>还没有案例。<Link to="/cases/new">创建第一个案例</Link></p>
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
                    {caseItem.description || '无描述'}
                  </p>
                  <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', fontSize: '0.9rem', color: '#888' }}>
                    <span>腔型: {getCavityTypeLabel(caseItem.cavity_type)}</span>
                    <span>创建时间: {new Date(caseItem.created_at).toLocaleDateString()}</span>
                    {caseItem.symptoms && caseItem.symptoms.length > 0 && (
                      <span>症状: {caseItem.symptoms.length}个</span>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', marginLeft: '1rem' }}>
                  <Link to={`/cases/${caseItem.id}/edit`} className="btn btn-secondary">
                    编辑
                  </Link>
                  <button
                    onClick={() => handleDelete(caseItem.id)}
                    className="btn btn-danger"
                  >
                    删除
                  </button>
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
