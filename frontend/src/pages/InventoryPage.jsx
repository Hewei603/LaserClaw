import React, { useEffect, useState } from 'react';
import { inventoryApi } from '../api/inventory';
import { useLanguage } from '../LanguageContext';

function coatingChip(coating) {
  const range = coating.wl_min_nm === coating.wl_max_nm
    ? `${coating.wl_min_nm}`
    : `${coating.wl_min_nm}-${coating.wl_max_nm}`;
  const value = coating.value_pct != null
    ? ` ${coating.value_type}${coating.comparator}${coating.value_pct}%`
    : '';
  return `${coating.surface}: ${coating.function}@${range}${value}`;
}

function InventoryPage() {
  const { t, te } = useLanguage();
  const [items, setItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);
  const [error, setError] = useState(null);
  const [importReport, setImportReport] = useState(null);
  const [importing, setImporting] = useState(false);
  const [filters, setFilters] = useState({ category: '', wavelengthNm: '', functionName: '' });
  const [nameQuery, setNameQuery] = useState('');
  const [showReview, setShowReview] = useState(false);
  const [matchForm, setMatchForm] = useState({ wavelength: '1064', functionName: 'HR', roc: '', minD: '', minR: '' });
  const [matchResult, setMatchResult] = useState(null);
  const [matching, setMatching] = useState(false);
  const [sources, setSources] = useState([]);

  useEffect(() => { loadItems(); loadSources(); }, []);

  const loadSources = async () => {
    try {
      setSources(await inventoryApi.listSources());
    } catch {
      setSources([]);
    }
  };

  const handleDeleteSource = async (sourceFile) => {
    if (!window.confirm(t('inventoryPage.confirmClearSource'))) return;
    try {
      await inventoryApi.clearItems(sourceFile);
      await Promise.all([loadItems(), loadSources()]);
    } catch (err) {
      setError(t('inventoryPage.deleteFailed') + err.message);
    }
  };

  const loadItems = async (override = {}, reviewFlag = showReview) => {
    setLoadingItems(true);
    setError(null);
    try {
      const merged = { ...filters, ...override };
      const data = await inventoryApi.listItems({
        category: merged.category || undefined,
        wavelengthNm: merged.wavelengthNm ? Number(merged.wavelengthNm) : undefined,
        functionName: merged.functionName || undefined,
        needsReview: reviewFlag,
        limit: 500,
      });
      setItems(data);
    } catch (err) {
      setError(t('inventoryPage.loadFailed') + err.message);
    } finally {
      setLoadingItems(false);
    }
  };

  const handleImport = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    setImporting(true);
    setError(null);
    try {
      const report = await inventoryApi.importWorkbook(file);
      setImportReport(report);
      event.target.value = '';
      await Promise.all([loadItems(), loadSources()]);
    } catch (err) {
      setError(t('inventoryPage.importFailed') + err.message);
    } finally {
      setImporting(false);
    }
  };

  const handleMatch = async (event) => {
    event.preventDefault();
    setMatching(true);
    setError(null);
    try {
      const surface = { wavelength_nm: Number(matchForm.wavelength), function: matchForm.functionName };
      // A reflectivity floor turns "HR" from a label into a hard判定:
      // R=85% nominal vs min_R_pct=99.5 → below_spec, exactly as documented.
      if (matchForm.minR.trim() && !Number.isNaN(Number(matchForm.minR))) {
        surface.min_R_pct = Number(matchForm.minR);
      }
      const requirement = {
        role: 'ui match',
        surfaces: [surface],
      };
      const rawRoc = matchForm.roc.trim().toLowerCase();
      if (rawRoc) {
        if (['flat', '平镜', '平', 'inf', '无限', '平面'].includes(rawRoc)) {
          requirement.roc_mm = 'flat';
        } else if (!Number.isNaN(Number(rawRoc))) {
          requirement.roc_mm = Number(rawRoc);
        } else {
          setError(t('inventoryPage.badRoc'));
          setMatching(false);
          return;
        }
      }
      if (matchForm.minD.trim()) requirement.min_diameter_mm = Number(matchForm.minD);
      const result = await inventoryApi.match(requirement);
      setMatchResult(result);
    } catch (err) {
      setError(t('inventoryPage.matchFailed') + err.message);
    } finally {
      setMatching(false);
    }
  };

  const geometry = (item) => {
    if (item.roc_is_flat) return t('inventoryPage.flat');
    const parts = [];
    if (item.roc_mm != null) parts.push(`R=${item.roc_mm}mm`);
    if (item.diameter_mm != null) parts.push(`D=${item.diameter_mm}mm`);
    if (item.dimensions) parts.push(item.dimensions);
    return parts.join(' · ') || '-';
  };

  return (
    <div>
      <div className="detail-header">
        <div>
          <h1>{t('inventoryPage.title')}</h1>
          <p className="muted">{t('inventoryPage.subtitle')}</p>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="grid-2">
        <div className="card">
          <h2 className="card-title">{t('inventoryPage.importTitle')}</h2>
          <input type="file" accept=".xlsx" onChange={handleImport} disabled={importing} />
          <p className="muted">{importing ? t('inventoryPage.importing') : t('inventoryPage.importHint')}</p>
          {importReport && (
            <div className="stat-row">
              <div className="stat-chip"><span className="stat-label">{t('inventoryPage.importedItems')}</span><span className="stat-value">{importReport.imported}</span></div>
              <div className="stat-chip"><span className="stat-label">{t('inventoryPage.coatingBands')}</span><span className="stat-value">{importReport.coating_bands}</span></div>
              <div className="stat-chip"><span className="stat-label">{t('inventoryPage.needsReview')}</span><span className="stat-value">{importReport.needs_review + importReport.partial}</span></div>
            </div>
          )}
          {sources.length > 0 && (
            <div style={{ marginTop: '0.75rem' }}>
              <h3>{t('inventoryPage.sourcesTitle')}</h3>
              {sources.map((source) => (
                <div key={source.source_file} className="source-row">
                  <span>{source.source_file} · {source.items}</span>
                  <button className="btn btn-danger" type="button" onClick={() => handleDeleteSource(source.source_file)}>
                    {t('inventoryPage.deleteSource')}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <form className="card" onSubmit={handleMatch}>
          <h2 className="card-title">{t('inventoryPage.matchTitle')}</h2>
          <p className="muted">{t('inventoryPage.matchHint')}</p>
          <div className="input-row">
            <label>
              {t('inventoryPage.reqWavelength')}
              <input value={matchForm.wavelength} onChange={(e) => setMatchForm({ ...matchForm, wavelength: e.target.value })} />
            </label>
            <label>
              {t('inventoryPage.reqFunction')}
              <select value={matchForm.functionName} onChange={(e) => setMatchForm({ ...matchForm, functionName: e.target.value })}>
                <option value="HR">HR</option>
                <option value="AR">AR</option>
                <option value="HT">HT</option>
                <option value="PR">PR</option>
              </select>
            </label>
          </div>
          <div className="input-row">
            <label>
              {t('inventoryPage.reqRoc')}
              <input value={matchForm.roc} onChange={(e) => setMatchForm({ ...matchForm, roc: e.target.value })} placeholder="400 / flat" />
            </label>
            <label>
              {t('inventoryPage.reqMinD')}
              <input value={matchForm.minD} onChange={(e) => setMatchForm({ ...matchForm, minD: e.target.value })} placeholder="12.7" />
            </label>
            <label>
              {t('inventoryPage.reqMinR')}
              <input value={matchForm.minR} onChange={(e) => setMatchForm({ ...matchForm, minR: e.target.value })} placeholder="99.5" title={t('inventoryPage.reqMinRHint')} />
            </label>
          </div>
          <p className="muted">{t('inventoryPage.reqMinRHint')}</p>
          <button className="btn btn-primary" type="submit" disabled={matching}>
            {matching ? t('inventoryPage.matching') : t('inventoryPage.matchBtn')}
          </button>
        </form>
      </div>

      {matchResult && (
        <div className="card">
          <h2 className="card-title">{t('inventoryPage.verdictTitle')}</h2>
          <p className="result-summary">{matchResult.summary}</p>
          {matchResult.candidates.map((c) => (
            <div key={c.item_id} className="source-row">
              <div>
                <strong>#{c.item_id} {c.name}</strong>
                <p className="muted">{c.raw_spec}</p>
                {(c.must_measure || []).length > 0 && (
                  <p className="muted">⚠ {t('caseDetail.modulesTab.mustMeasure')}: {c.must_measure.join('；')}</p>
                )}
              </div>
              <span className={`meta-pill ${c.frontier ? 'pill-frontier' : ''}`}>
                {c.frontier ? t('caseDetail.modulesTab.frontier') : t('caseDetail.modulesTab.eligible')}
              </span>
            </div>
          ))}
          {Object.keys(matchResult.rejection_reasons || {}).length > 0 && (
            <div>
              <h3>{t('caseDetail.modulesTab.matchRejected')}</h3>
              <div className="stat-row">
                {Object.entries(matchResult.rejection_reasons).map(([reason, count]) => (
                  <div key={reason} className="stat-chip"><span className="stat-label">{reason}</span><span className="stat-value">×{count}</span></div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h2 className="card-title">{t('inventoryPage.filterTitle')}</h2>
        <div className="input-row">
          <label>
            {t('inventoryPage.category')}
            <select value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
              <option value="">{t('inventoryPage.anyCategory')}</option>
              <option value="mirror">{t('inventoryPage.catMirror')}</option>
              <option value="lens">{t('inventoryPage.catLens')}</option>
              <option value="gain_crystal">{t('inventoryPage.catGain')}</option>
              <option value="nonlinear_crystal">{t('inventoryPage.catNonlinear')}</option>
            </select>
          </label>
          <label>
            {t('inventoryPage.wavelength')}
            <input value={filters.wavelengthNm} onChange={(e) => setFilters({ ...filters, wavelengthNm: e.target.value })} placeholder="1064" />
          </label>
          <label>
            {t('inventoryPage.functionLabel')}
            <select value={filters.functionName} onChange={(e) => setFilters({ ...filters, functionName: e.target.value })}>
              <option value="">{t('inventoryPage.anyFunction')}</option>
              <option value="HR">HR</option>
              <option value="AR">AR / HT</option>
              <option value="PR">PR</option>
            </select>
          </label>
          <label>
            {t('inventoryPage.nameFilter')}
            <input value={nameQuery} onChange={(e) => setNameQuery(e.target.value)} placeholder="拉曼 / SESAM ..." />
          </label>
          <button className="btn btn-primary" onClick={() => loadItems()} type="button">{t('inventoryPage.searchBtn')}</button>
        </div>
        <label className="checkbox-row">
          <input type="checkbox" checked={showReview}
            onChange={(e) => { setShowReview(e.target.checked); loadItems({}, e.target.checked); }} />
          {t('inventoryPage.reviewQueueTitle')}
        </label>
      </div>

      <div className="card">
        <p className="muted">{t('inventoryPage.totalItems')} {items.filter((i) => i.name.toLowerCase().includes(nameQuery.trim().toLowerCase())).length} {t('inventoryPage.itemsUnit')}</p>
        {items.length >= 500 && <div className="disclaimer">{t('inventoryPage.truncated')}</div>}
        {loadingItems ? <p>{t('common.loading')}</p> : items.length === 0 ? (
          <p>{t('inventoryPage.noItems')}</p>
        ) : (
          <div className="table-scroll">
          <table className="mini-table wide">
            <thead>
              <tr>
                <th>{t('inventoryPage.colName')}</th>
                <th>{t('inventoryPage.colGeometry')}</th>
                <th>{t('inventoryPage.colCoatings')}</th>
                <th className="num">{t('inventoryPage.colQty')}</th>
                <th>{t('inventoryPage.colLocation')}</th>
              </tr>
            </thead>
            <tbody>
              {items.filter((i) => i.name.toLowerCase().includes(nameQuery.trim().toLowerCase())).map((item) => (
                <tr key={item.id} className={item.parse_confidence !== 'parsed' ? 'row-review' : ''}>
                  <td className="name-cell"><strong>{item.name}</strong>{item.condition !== 'ok' && (
                    <span className="meta-pill">{te(item.condition)}</span>
                  )}</td>
                  <td>{geometry(item)}</td>
                  <td>
                    {(item.coatings || []).slice(0, 4).map((coating) => (
                      <span key={coating.id} className="meta-pill">{coatingChip(coating)}</span>
                    ))}
                    {(item.coatings || []).length > 4 && <span className="muted">+{item.coatings.length - 4}</span>}
                  </td>
                  <td className="num">{item.quantity}</td>
                  <td>{item.location || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default InventoryPage;
