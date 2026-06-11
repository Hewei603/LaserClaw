import React, { useEffect, useRef, useState } from 'react';
import { knowledgeApi } from '../api/knowledge';
import { useLanguage } from '../LanguageContext';

const ACCEPTED_TYPES = '.pdf,.txt,.md,.csv,.json,.log';

function formatDate(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('zh-CN', { dateStyle: 'short', timeStyle: 'short' });
}

export default function LabDocuments() {
  const { t } = useLanguage();
  const [sources, setSources] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    loadSources();
  }, []);

  const loadSources = async () => {
    try {
      const data = await knowledgeApi.listSources();
      setSources(data.filter((source) => !source.case_id));
    } catch (err) {
      setUploadError(err.message);
    }
  };

  const handleFiles = async (files) => {
    if (!files || files.length === 0) return;
    setUploadError(null);
    setUploading(true);
    const errors = [];
    for (const file of Array.from(files)) {
      try {
        await knowledgeApi.uploadGlobalSource(file);
      } catch (err) {
        errors.push(`${file.name}: ${err.response?.data?.detail || err.message}`);
      }
    }
    setUploading(false);
    if (errors.length > 0) setUploadError(errors.join('\n'));
    await loadSources();
  };

  const handleFileInput = (event) => handleFiles(event.target.files);

  const handleDrop = (event) => {
    event.preventDefault();
    setDragOver(false);
    handleFiles(event.dataTransfer.files);
  };

  const handleDelete = async (source) => {
    if (!window.confirm(t('labDocsPage.deleteConfirm'))) return;
    setDeletingId(source.id);
    try {
      await knowledgeApi.deleteSource(source.id);
      setSources((prev) => prev.filter((item) => item.id !== source.id));
    } catch (err) {
      setUploadError(err.response?.data?.detail || err.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="lab-docs-page">
      <div className="lab-docs-header">
        <h1>{t('labDocsPage.title')}</h1>
        <p className="lab-docs-subtitle">{t('labDocsPage.subtitle')}</p>
      </div>

      <div
        className={`lab-docs-dropzone${dragOver ? ' dragover' : ''}`}
        onDragOver={(event) => { event.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => event.key === 'Enter' && fileInputRef.current?.click()}
        aria-label={t('labDocsPage.dropzone')}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          style={{ display: 'none' }}
          onChange={handleFileInput}
        />
        {uploading ? (
          <span className="lab-docs-uploading">{t('labDocsPage.uploading')}</span>
        ) : (
          <>
            <span className="lab-docs-dropzone-icon">+</span>
            <span className="lab-docs-dropzone-text">{t('labDocsPage.dropzone')}</span>
            <span className="lab-docs-dropzone-hint">{t('labDocsPage.dropzoneHint')}</span>
          </>
        )}
      </div>

      {uploadError && (
        <div className="lab-docs-error" role="alert">
          <strong>{t('labDocsPage.uploadFailed')}</strong>
          <pre>{uploadError}</pre>
        </div>
      )}

      <div className="lab-docs-list-header">
        <h2>{t('labDocsPage.listTitle')} <span className="lab-docs-count">{sources.length}</span></h2>
      </div>

      {sources.length === 0 ? (
        <div className="lab-docs-empty">{t('labDocsPage.empty')}</div>
      ) : (
        <table className="lab-docs-table" aria-label={t('labDocsPage.listTitle')}>
          <thead>
            <tr>
              <th>{t('labDocsPage.colName')}</th>
              <th>{t('labDocsPage.colType')}</th>
              <th>{t('labDocsPage.colChunks')}</th>
              <th>{t('labDocsPage.colDate')}</th>
              <th aria-label={t('labDocsPage.colAction')}></th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr key={source.id}>
                <td className="lab-docs-title">
                  <span className="lab-docs-filename">{source.title}</span>
                </td>
                <td>
                  <span className="lab-docs-badge">{source.source_type}</span>
                </td>
                <td>{source.chunk_count ?? '-'}</td>
                <td>{formatDate(source.created_at)}</td>
                <td>
                  <button
                    className="lab-docs-delete-btn"
                    onClick={() => handleDelete(source)}
                    disabled={deletingId === source.id}
                    aria-label={`${t('common.delete')} ${source.title}`}
                  >
                    {deletingId === source.id ? `${t('common.delete')}...` : t('common.delete')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
