import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { casesApi } from '../api/cases';

export default function CaseForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [loading, setLoading] = useState(Boolean(id));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!id) return;
    let alive = true;
    casesApi.get(id).then(data => {
      if (alive) { setTitle(data.title); setDescription(data.description || ''); }
    }).catch(err => { if (alive) setError(err.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [id]);
  const submit = async event => {
    event.preventDefault();
    setSaving(true); setError('');
    try {
      const data = { title: title.trim(), description: description.trim() };
      const saved = id ? await casesApi.update(id, data) : await casesApi.create(data);
      navigate(`/cases/${saved.id}`);
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };
  return <div className="page-container" style={{ maxWidth: 780, margin: '0 auto' }}>
    <Link to={id ? `/cases/${id}` : '/cases'}>← 返回案例</Link>
    <h1>{id ? '编辑案例' : '从一个实验想法开始'}</h1>
    <p className="text-muted">先写目标和已有条件。进入设计工作区后，直接与 Agent 对话、上传元件标签，再计算光路和选型。</p>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {loading ? <p>加载中…</p> : <form className="card" onSubmit={submit}>
      <div className="form-group"><label htmlFor="case-title">案例标题</label>
        <input id="case-title" required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：808 nm 泵浦 Nd:YVO4 直线腔" /></div>
      <div className="form-group"><label htmlFor="case-description">描述 / 备注（选填）</label>
        <textarea id="case-description" rows={8} maxLength={20000} value={description} onChange={e => setDescription(e.target.value)} placeholder="想得到什么结果？手头有哪些器件？哪些参数还不知道？按自己的话写即可。" /></div>
      <button className="btn btn-primary" disabled={saving || !title.trim()}>{saving ? '保存中…' : id ? '保存并返回设计' : '创建并进入设计工作区 →'}</button>
    </form>}
  </div>;
}
