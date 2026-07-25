import React from 'react';
import { useLanguage } from '../LanguageContext';

/** Typed, human-readable renderers for physics/measurement module results.
 *  Falls back to nothing when the result shape is missing — the caller keeps
 *  the collapsible raw-JSON view for full detail. */

function StatChips({ items }) {
  return (
    <div className="stat-row">
      {items.filter(([, v]) => v !== undefined && v !== null && v !== '').map(([label, value]) => (
        <div key={label} className="stat-chip">
          <span className="stat-label">{label}</span>
          <span className="stat-value">{String(value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Fitted power-curve line as a small SVG: threshold marker + linear region. */
function PowerCurveChart({ fit, units, data }) {
  if (!fit || fit.threshold_pump == null || !fit.fit_line) return null;
  const pumpMax = Math.max(fit.at_max_pump || 0, fit.threshold_pump * 1.2, 1e-9);
  const outMax = Math.max(fit.max_output || 0, 1e-9);
  const W = 420; const H = 190; const PAD = 40;
  const x = (p) => PAD + (p / pumpMax) * (W - PAD - 10);
  const y = (o) => H - PAD + 10 - (o / outMax) * (H - PAD - 22);
  const thX = x(Math.max(fit.threshold_pump, 0));
  const endY = y(fit.fit_line.a * pumpMax + fit.fit_line.b);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg className="power-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="power curve">
      <line x1={PAD} y1={H - PAD + 10} x2={W - 6} y2={H - PAD + 10} className="axis" />
      <line x1={PAD} y1={8} x2={PAD} y2={H - PAD + 10} className="axis" />
      {ticks.map((f) => (
        <g key={`xt${f}`}>
          <line x1={x(f * pumpMax)} y1={H - PAD + 10} x2={x(f * pumpMax)} y2={H - PAD + 14} className="axis" />
          <text x={x(f * pumpMax)} y={H - PAD + 26} textAnchor="middle" className="chart-note">{(f * pumpMax).toFixed(1)}</text>
        </g>
      ))}
      {ticks.map((f) => (
        <g key={`yt${f}`}>
          <line x1={PAD - 4} y1={y(f * outMax)} x2={PAD} y2={y(f * outMax)} className="axis" />
          <text x={PAD - 7} y={y(f * outMax) + 3.5} textAnchor="end" className="chart-note">{(f * outMax).toFixed(1)}</text>
        </g>
      ))}
      <line x1={x(0)} y1={y(0)} x2={thX} y2={y(0)} className="fit-flat" />
      <line x1={thX} y1={y(0)} x2={x(pumpMax)} y2={endY} className="fit-line" />
      {(data?.pump || []).map((p, i) => (
        <circle key={i} cx={x(p)} cy={y(data.output[i])} r="2.6" className="data-point" />
      ))}
      <line x1={thX} y1={y(0)} x2={thX} y2={16} className="threshold-mark" />
      <text x={thX + 4} y={26} className="chart-note">P_th={fit.threshold_pump}</text>
      <text x={W - 8} y={H - 4} textAnchor="end" className="chart-note">{units?.pump || ''}</text>
      <text x={PAD + 4} y={14} className="chart-note">{units?.output || ''}</text>
    </svg>
  );
}

export function PowerCurveResult({ result, showComparison = true }) {
  const { t } = useLanguage();
  const fit = result.fit;
  if (!fit) return null;
  return (
    <div className="generated-section">
      <StatChips items={[
        [t('caseDetail.modulesTab.threshold'), `${fit.threshold_pump} ${result.units?.pump || ''}`],
        [t('caseDetail.modulesTab.slopeEff'), `${fit.slope_efficiency_pct}%`],
        ['R²', fit.r_squared],
        ['T_oc', result.output_coupler_T_pct != null ? `${result.output_coupler_T_pct}%` : null],
      ]} />
      <PowerCurveChart fit={fit} units={result.units} data={result.data} />
      {(fit.warnings || []).map((w) => <div key={w} className="disclaimer">{w}</div>)}
      {showComparison && result.comparison && result.comparison.length > 1 && (
        <div>
          <h3>{t('caseDetail.modulesTab.seriesCompare')}</h3>
          <table className="mini-table">
            <thead><tr><th>{t('caseDetail.modulesTab.colSeries')}</th><th className="num">T_oc</th><th className="num">{t('caseDetail.modulesTab.threshold')}</th><th className="num">{t('caseDetail.modulesTab.slopeEff')}</th></tr></thead>
            <tbody>
              {result.comparison.map((s) => (
                <tr key={s.module_id}>
                  <td>{s.label}</td>
                  <td className="num">{s.output_coupler_T_pct != null ? `${s.output_coupler_T_pct}%` : '-'}</td>
                  <td className="num">{s.threshold_pump}</td>
                  <td className="num">{s.slope_efficiency_pct != null ? `${s.slope_efficiency_pct}%` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.findlay_clay?.applicable && (
            <StatChips items={[
              [`${t('caseDetail.modulesTab.cavityLoss')} (Findlay-Clay)`, `${result.findlay_clay.round_trip_loss_pct}%`],
              ['Caird η₀', result.caird?.applicable ? `${result.caird.intrinsic_slope_pct}%` : null],
            ]} />
          )}
        </div>
      )}
    </div>
  );
}

export function CavityDesignResult({ result }) {
  const { t, lang, te } = useLanguage();
  const rec = result.recommended || result.analysis;
  const summary = lang === 'zh' && rec?.length_mm != null
    ? `推荐腔长 L = ${rec.length_mm} mm，束腰 w0 = ${rec.waist_w0_mm} mm`
    : result.summary;
  return (
    <div className="generated-section">
      {summary && <p className="result-summary">{summary}</p>}
      {result.scan?.stable_windows_mm && (
        <StatChips items={[[t('caseDetail.modulesTab.stableWindows'),
          result.scan.stable_windows_mm.map(([a, b]) => `${a} – ${b} mm`).join('；')]]} />
      )}
      {rec && (
        <div>
          <h3>{t('caseDetail.modulesTab.recommended')}</h3>
          <StatChips items={[
            ['L (mm)', rec.length_mm],
            ['w0 (mm)', rec.waist_w0_mm],
            ['w@M1 (mm)', rec.w_on_mirror1_mm],
            ['w@M2 (mm)', rec.w_on_mirror2_mm],
            ['w@crystal (mm)', rec.w_in_crystal_mm],
            ['|m|', rec.stability_m != null ? Math.abs(rec.stability_m).toFixed(3) : null],
          ]} />
        </div>
      )}
      {result.placement && (
        <div>
          <h3>{t('caseDetail.modulesTab.placement')}</h3>
          <table className="mini-table">
            <tbody>
              {result.placement.map((p) => (
                <tr key={p.element}><td>{te(p.element)}</td><td className="num">{p.position_mm} mm</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function PhaseMatchResult({ result }) {
  const { t, lang, te } = useLanguage();
  if (!result.solutions) return null;
  const matched = result.solutions.filter((s) => s.theta_deg != null);
  const summary = lang === 'zh'
    ? `共 ${matched.length} 个相位匹配解 → ${matched[0] ? `${matched[0].lambda3_nm} nm` : '无'}`
    : result.summary;
  return (
    <div className="generated-section">
      {summary && <p className="result-summary">{summary}</p>}
      <h3>{t('caseDetail.modulesTab.pmSolutions')}</h3>
      <table className="mini-table">
        <thead><tr><th>{t('caseDetail.modulesTab.colPlane')}</th><th className="num">θ (°)</th><th className="num">φ (°)</th><th className="num">λ₃ (nm)</th><th className="num">{t('caseDetail.modulesTab.colWalkoff')}</th><th>{t('caseDetail.modulesTab.colConfidence')}</th></tr></thead>
        <tbody>
          {matched.map((s, i) => (
            <tr key={i}>
              <td>{s.plane || 'uniaxial'}</td>
              <td className="num">{s.theta_deg}</td>
              <td className="num">{s.phi_deg ?? '-'}</td>
              <td className="num">{s.lambda3_nm}</td>
              <td className="num">{s.walkoff_mrad != null ? `${s.walkoff_mrad} mrad` : '-'}</td>
              <td><span className={`meta-pill conf-${s.confidence}`}>{te(s.confidence)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      {matched.length === 0 && <p className="muted">{result.summary}</p>}
    </div>
  );
}

export function CoatingTmmResult({ result }) {
  const { t, lang, te } = useLanguage();
  const sb = result.stopband;
  const summary = lang === 'zh' && sb?.edges_nm
    ? `原型阻带约 ${Math.round(sb.edges_nm[0])} – ${Math.round(sb.edges_nm[1])} nm（中心 ${sb.center_nm} nm）`
    : result.summary;
  return (
    <div className="generated-section">
      {summary && <p className="result-summary">{summary}</p>}
      <div className="stat-row">
        {(result.query_results || []).map((q) => (
          <div key={q.wavelength_nm} className={`stat-chip band-${q.band_position}`}>
            <span className="stat-label">{q.wavelength_nm} nm</span>
            <span className="stat-value">{te(q.band_position)}{q.margin_to_edge_nm != null ? ` (${q.margin_to_edge_nm}nm)` : ''}</span>
          </div>
        ))}
      </div>
      {result.stopband && (
        <StatChips items={[
          [t('caseDetail.modulesTab.stopbandLabel'), `${result.stopband.edges_nm?.[0]} – ${result.stopband.edges_nm?.[1]}`],
          [t('caseDetail.modulesTab.confidenceLabel'), result.confidence],
        ]} />
      )}
      {result.disclaimer && <div className="disclaimer">{lang === 'zh' ? t('caseDetail.modulesTab.coatingDisclaimer') : result.disclaimer}</div>}
    </div>
  );
}

export function ComponentMatchResult({ result }) {
  const { t } = useLanguage();
  if (!result.candidates) return null;
  return (
    <div className="generated-section">
      {result.summary && <p className="result-summary">{result.summary}</p>}
      <h3>{t('caseDetail.modulesTab.matchCandidates')}</h3>
      {result.candidates.map((c) => (
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
      {result.rejection_reasons && Object.keys(result.rejection_reasons).length > 0 && (
        <div>
          <h3>{t('caseDetail.modulesTab.matchRejected')}</h3>
          <div className="stat-row">
            {Object.entries(result.rejection_reasons).map(([reason, count]) => (
              <div key={reason} className="stat-chip"><span className="stat-label">{reason}</span><span className="stat-value">×{count}</span></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function ModuleResult({ moduleType, result, showComparison = true }) {
  if (!result || result.status === 'needs_input') {
    return result?.message ? <div className="disclaimer">{result.message}</div> : null;
  }
  if (moduleType === 'power_curve') return <PowerCurveResult result={result} showComparison={showComparison} />;
  if (moduleType === 'cavity_design') return <CavityDesignResult result={result} />;
  if (moduleType === 'phase_match') return <PhaseMatchResult result={result} />;
  if (moduleType === 'coating_tmm') return <CoatingTmmResult result={result} />;
  if (moduleType === 'component_match') return <ComponentMatchResult result={result} />;
  return result.summary ? <p className="result-summary">{result.summary}</p> : null;
}
