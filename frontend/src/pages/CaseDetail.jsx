import React, { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { casesApi } from '../api/cases';

function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [caseData, setCaseData] = useState(null);
  const [generatedContents, setGeneratedContents] = useState({});
  const [attachments, setAttachments] = useState([]);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState({});
  const [error, setError] = useState(null);
  const [uploadFile, setUploadFile] = useState(null);

  useEffect(() => {
    loadData();
  }, [id]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [caseResult, contentsResult, attachmentsResult] = await Promise.all([
        casesApi.get(id),
        casesApi.getGeneratedContents(id),
        casesApi.listAttachments(id)
      ]);

      setCaseData(caseResult);
      setAttachments(attachmentsResult);

      // 组织生成的内容
      const organized = {};
      contentsResult.forEach(item => {
        if (!organized[item.content_type]) {
          organized[item.content_type] = [];
        }
        organized[item.content_type].push(item);
      });
      setGeneratedContents(organized);

      setError(null);
    } catch (err) {
      setError('加载数据失败: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async (type) => {
    setGenerating(prev => ({ ...prev, [type]: true }));
    try {
      let result;
      switch (type) {
        case 'plan':
          result = await casesApi.generatePlan(id);
          break;
        case 'rezonator':
          result = await casesApi.generateRezonator(id);
          break;
        case 'troubleshooting':
          result = await casesApi.generateTroubleshooting(id);
          break;
        case 'report':
          result = await casesApi.generateReport(id);
          break;
      }
      await loadData();
    } catch (err) {
      alert('生成失败: ' + err.message);
    } finally {
      setGenerating(prev => ({ ...prev, [type]: false }));
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
      await casesApi.uploadAttachment(id, file);
      await loadData();
      e.target.value = '';
    } catch (err) {
      alert('上传失败: ' + err.message);
    }
  };

  const handleDeleteAttachment = async (attachmentId) => {
    if (!window.confirm('确定要删除这个附件吗？')) return;

    try {
      await casesApi.deleteAttachment(attachmentId);
      await loadData();
    } catch (err) {
      alert('删除失败: ' + err.message);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm('确定要删除这个案例吗？')) return;

    try {
      await casesApi.delete(id);
      navigate('/cases');
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

  const renderContent = (content) => {
    return (
      <pre style={{
        backgroundColor: '#1a1825',
        padding: '1rem',
        borderRadius: '4px',
        overflow: 'auto',
        whiteSpace: 'pre-wrap',
        wordWrap: 'break-word'
      }}>
        {JSON.stringify(content, null, 2)}
      </pre>
    );
  };

  const getLatestContent = (type) => {
    const contents = generatedContents[type];
    return contents && contents.length > 0 ? contents[0] : null;
  };

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  if (error) {
    return <div className="error">{error}</div>;
  }

  if (!caseData) {
    return <div className="error">案例不存在</div>;
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '2rem' }}>
        <div>
          <h1>{caseData.title}</h1>
          <p style={{ color: '#888', marginTop: '0.5rem' }}>
            创建时间: {new Date(caseData.created_at).toLocaleString()}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <Link to={`/cases/${id}/edit`} className="btn btn-secondary">
            编辑
          </Link>
          <button onClick={handleDelete} className="btn btn-danger">
            删除
          </button>
        </div>
      </div>

      {/* 标签页导航 */}
      <div style={{
        display: 'flex',
        gap: '1rem',
        borderBottom: '1px solid #2a2838',
        marginBottom: '2rem'
      }}>
        {['overview', 'plan', 'rezonator', 'troubleshooting', 'report', 'attachments'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '0.75rem 1rem',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #6c8eef' : '2px solid transparent',
              color: activeTab === tab ? '#6c8eef' : '#888',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
          >
            {tab === 'overview' && '概览'}
            {tab === 'plan' && '实验计划'}
            {tab === 'rezonator' && 'ReZonator模式'}
            {tab === 'troubleshooting' && '故障排查'}
            {tab === 'report' && '实验报告'}
            {tab === 'attachments' && '附件'}
          </button>
        ))}
      </div>

      {/* 概览标签 */}
      {activeTab === 'overview' && (
        <div>
          <div className="card">
            <h2 className="card-title">基本信息</h2>
            <div style={{ marginTop: '1rem' }}>
              <p><strong>描述:</strong> {caseData.description || '无'}</p>
              <p style={{ marginTop: '0.5rem' }}><strong>腔型:</strong> {getCavityTypeLabel(caseData.cavity_type)}</p>
              <p style={{ marginTop: '0.5rem' }}><strong>实验目标:</strong> {caseData.goal}</p>
            </div>
          </div>

          <div className="card">
            <h2 className="card-title">关键参数</h2>
            {Object.keys(caseData.parameters).length === 0 ? (
              <p className="card-content">无参数</p>
            ) : (
              <div style={{ marginTop: '1rem' }}>
                {Object.entries(caseData.parameters).map(([key, value]) => (
                  <p key={key} style={{ marginBottom: '0.5rem' }}>
                    <strong>{key}:</strong> {value}
                  </p>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="card-title">观察到的症状</h2>
            {caseData.symptoms.length === 0 ? (
              <p className="card-content">无症状</p>
            ) : (
              <ul style={{ marginTop: '1rem', paddingLeft: '1.5rem' }}>
                {caseData.symptoms.map((symptom, idx) => (
                  <li key={idx} style={{ marginBottom: '0.5rem' }}>{symptom}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {/* 实验计划标签 */}
      {activeTab === 'plan' && (
        <div>
          {getLatestContent('plan') ? (
            <div>
              {getLatestContent('plan').content.disclaimer && (
                <div className="disclaimer">{getLatestContent('plan').content.disclaimer}</div>
              )}
              {renderContent(getLatestContent('plan').content)}
            </div>
          ) : (
            <div className="card">
              <p>还没有生成实验计划</p>
              <button
                onClick={() => handleGenerate('plan')}
                className="btn btn-primary"
                style={{ marginTop: '1rem' }}
                disabled={generating.plan}
              >
                {generating.plan ? '生成中...' : '生成实验计划'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* ReZonator模式标签 */}
      {activeTab === 'rezonator' && (
        <div>
          {getLatestContent('rezonator') ? (
            <div>
              {getLatestContent('rezonator').content.disclaimer && (
                <div className="disclaimer">{getLatestContent('rezonator').content.disclaimer}</div>
              )}
              {renderContent(getLatestContent('rezonator').content)}
            </div>
          ) : (
            <div className="card">
              <p>还没有生成ReZonator模式</p>
              <button
                onClick={() => handleGenerate('rezonator')}
                className="btn btn-primary"
                style={{ marginTop: '1rem' }}
                disabled={generating.rezonator}
              >
                {generating.rezonator ? '生成中...' : '生成ReZonator模式'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 故障排查标签 */}
      {activeTab === 'troubleshooting' && (
        <div>
          {getLatestContent('troubleshooting') ? (
            <div>
              {getLatestContent('troubleshooting').content.disclaimer && (
                <div className="disclaimer">{getLatestContent('troubleshooting').content.disclaimer}</div>
              )}
              {renderContent(getLatestContent('troubleshooting').content)}
            </div>
          ) : (
            <div className="card">
              <p>还没有生成故障排查建议</p>
              <button
                onClick={() => handleGenerate('troubleshooting')}
                className="btn btn-primary"
                style={{ marginTop: '1rem' }}
                disabled={generating.troubleshooting}
              >
                {generating.troubleshooting ? '生成中...' : '生成故障排查'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 实验报告标签 */}
      {activeTab === 'report' && (
        <div>
          {getLatestContent('report') ? (
            <div>
              {getLatestContent('report').content.disclaimer && (
                <div className="disclaimer">{getLatestContent('report').content.disclaimer}</div>
              )}
              {renderContent(getLatestContent('report').content)}
            </div>
          ) : (
            <div className="card">
              <p>还没有生成实验报告</p>
              <button
                onClick={() => handleGenerate('report')}
                className="btn btn-primary"
                style={{ marginTop: '1rem' }}
                disabled={generating.report}
              >
                {generating.report ? '生成中...' : '生成实验报告'}
              </button>
            </div>
          )}
        </div>
      )}

      {/* 附件标签 */}
      {activeTab === 'attachments' && (
        <div>
          <div className="card">
            <h2 className="card-title">上传附件</h2>
            <input
              type="file"
              onChange={handleFileUpload}
              style={{ marginTop: '1rem' }}
            />
          </div>

          {attachments.length === 0 ? (
            <div className="card">
              <p>还没有附件</p>
            </div>
          ) : (
            <div>
              {attachments.map(attachment => (
                <div key={attachment.id} className="card">
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <p><strong>{attachment.filename}</strong></p>
                      <p style={{ fontSize: '0.9rem', color: '#888', marginTop: '0.25rem' }}>
                        类型: {attachment.file_type || '未知'} |
                        上传时间: {new Date(attachment.uploaded_at).toLocaleString()}
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <a
                        href={`http://localhost:8000/api/attachments/${attachment.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-secondary"
                      >
                        下载
                      </a>
                      <button
                        onClick={() => handleDeleteAttachment(attachment.id)}
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
      )}
    </div>
  );
}

export default CaseDetail;
