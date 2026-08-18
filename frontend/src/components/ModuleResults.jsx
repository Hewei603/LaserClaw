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

/** Cavity layout: element positions to scale along z, beam envelope exaggerated.
 *
 *  Every number here is computed by the backend kernel (`beam_envelope` +
 *  `element_placement`); this only maps mm to pixels. Nothing Gaussian is
 *  recomputed in the browser — that is the whole point of having a kernel.
 *
 *  The vertical axis cannot be to scale: a 0.25 mm beam in an 85 mm cavity would
 *  be a hairline. It is exaggerated by a factor that is printed on the drawing,
 *  because an unlabelled distortion is just a wrong picture.
 */
export function CavityLayoutDiagram({ placement, envelope }) {
  const { t, te } = useLanguage();
  const points = envelope?.points || [];
  if (!placement?.length || points.length < 2) return null;

  const W = 460; const H = 150;
  const PAD_X = 30; const AXIS_Y = 78; const HALF = 44;

  const zEnd = placement[placement.length - 1]?.position_mm || points[points.length - 1].z_mm;
  if (!zEnd) return null;

  const maxW = Math.max(...points.map((p) => p.w_mm));
  // Round the exaggeration to something a person can hold in their head.
  const rawScale = HALF / maxW;
  const magnification = Math.max(1, Math.round(rawScale / (zEnd / (W - 2 * PAD_X))));

  const x = (mm) => PAD_X + (mm / zEnd) * (W - 2 * PAD_X);
  const halfHeight = (w) => (w / maxW) * HALF;

  const upper = points.map((p) => `${x(p.z_mm).toFixed(2)},${(AXIS_Y - halfHeight(p.w_mm)).toFixed(2)}`);
  const lower = [...points].reverse().map(
    (p) => `${x(p.z_mm).toFixed(2)},${(AXIS_Y + halfHeight(p.w_mm)).toFixed(2)}`,
  );
  const beamPath = `M${upper.join(' L')} L${lower.join(' L')} Z`;

  const mirrors = placement.filter((p) => /Mirror/i.test(p.element));
  const crystalFaces = placement.filter((p) => /Crystal/i.test(p.element));
  const crystal = crystalFaces.length === 2
    ? { from: crystalFaces[0].position_mm, to: crystalFaces[1].position_mm }
    : null;

  return (
    <div>
      <svg className="cavity-diagram" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={t('caseDetail.physics.layoutTitle')}>
        <line className="axis" x1={PAD_X} y1={AXIS_Y} x2={W - PAD_X} y2={AXIS_Y} strokeDasharray="3 3" />

        {crystal && (
          <g>
            <rect className="crystal" x={x(crystal.from)} y={AXIS_Y - HALF - 6}
              width={Math.max(x(crystal.to) - x(crystal.from), 1.5)} height={(HALF + 6) * 2} />
            <text className="chart-note" x={(x(crystal.from) + x(crystal.to)) / 2} y={AXIS_Y - HALF - 12}
              textAnchor="middle">{t('caseDetail.physics.crystalLabel')}</text>
          </g>
        )}

        <path className="beam" d={beamPath} />

        {envelope.waist && (
          <g>
            <line className="waist-mark" x1={x(envelope.waist.z_mm)} y1={AXIS_Y - HALF - 4}
              x2={x(envelope.waist.z_mm)} y2={AXIS_Y + HALF + 4} />
            <text className="chart-note" x={x(envelope.waist.z_mm)} y={AXIS_Y + HALF + 18}
              textAnchor="middle">w₀={envelope.waist.w0_mm} mm</text>
          </g>
        )}

        {mirrors.map((m, i) => {
          const mx = x(m.position_mm);
          const bulge = i === 0 ? 9 : -9;   // concave faces point into the cavity
          return (
            <g key={m.element}>
              <path className="mirror"
                d={`M${mx},${AXIS_Y - HALF - 6} Q${mx + bulge},${AXIS_Y} ${mx},${AXIS_Y + HALF + 6}`} />
              <text className="chart-note" x={mx} y={AXIS_Y - HALF - 12}
                textAnchor={i === 0 ? 'start' : 'end'}>{te(m.element)}</text>
              <text className="chart-note" x={mx} y={H - 8}
                textAnchor={i === 0 ? 'start' : 'end'}>{m.position_mm} mm</text>
            </g>
          );
        })}

        {crystalFaces.map((f) => (
          <text key={f.element} className="chart-note" x={x(f.position_mm)} y={H - 8}
            textAnchor="middle">{f.position_mm}</text>
        ))}
      </svg>
      <p className="muted diagram-caption">
        {t('caseDetail.physics.layoutScale').replace('{n}', magnification)}
        {envelope.note ? ` ${envelope.note}` : ''}
      </p>
    </div>
  );
}

/** Element positions as a drawing plus the exact table, always from one source. */
export function PlacementBlock({ placement, envelope }) {
  const { t, te } = useLanguage();
  if (!placement?.length) return null;
  return (
    <div>
      <h3>{t('caseDetail.physics.placement')}</h3>
      <CavityLayoutDiagram placement={placement} envelope={envelope} />
      <table className="mini-table">
        <tbody>
          {placement.map((p) => (
            <tr key={p.element}><td>{te(p.element)}</td><td className="num">{p.position_mm} mm</td></tr>
          ))}
        </tbody>
      </table>
    </div>
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
          {/* The two-point-fit warning ("R²=1 is meaningless, measure a third
              curve") exists precisely to stop this number going into a paper
              unqualified — swallowing it defeats the analysis. */}
          {result.findlay_clay?.applicable === false && result.findlay_clay?.note && (
            <div className="disclaimer">{t('caseDetail.modulesTab.fcNotApplicable')}{result.findlay_clay.note}</div>
          )}
          {[result.findlay_clay?.warning, result.caird?.warning].filter(Boolean).map((w) => (
            <div key={w} className="disclaimer">{w}</div>
          ))}
          {result.caird?.applicable === false && result.caird?.note && (
            <div className="disclaimer">Caird: {result.caird.note}</div>
          )}
        </div>
      )}
    </div>
  );
}

export function CavityDesignResult({ result }) {
  const { t } = useLanguage();
  const rec = result.recommended || result.analysis;
  // A fixed-length analysis of an UNSTABLE geometry must never read like a
  // recommendation — the student would go build a cavity that cannot lase.
  const unstable = rec && rec.stable === false;
  return (
    <div className="generated-section">
      {unstable && <div className="error">{t('caseDetail.modulesTab.unstableWarn')}</div>}
      {result.summary && <p className="result-summary">{result.summary}</p>}
      {result.scan?.stable_windows_mm && (
        <StatChips items={[[t('caseDetail.modulesTab.stableWindows'),
          result.scan.stable_windows_mm.length
            ? result.scan.stable_windows_mm.map(([a, b]) => `${a} – ${b} mm`).join('；')
            : '—']]} />
      )}
      {rec && !unstable && (
        <div>
          <h3>{t('caseDetail.modulesTab.recommended')}</h3>
          <StatChips items={[
            ['L (mm)', rec.length_mm],
            ['w0 (mm)', rec.waist_w0_mm],
            ['w@M1 (mm)', rec.w_on_mirror1_mm],
            ['w@M2 (mm)', rec.w_on_mirror2_mm],
            ['w@crystal (mm)', rec.w_in_crystal_mm],
            [t('caseDetail.modulesTab.thermalTol'),
              rec.thermal_lens_tolerance_dioptre != null ? `${rec.thermal_lens_tolerance_dioptre} D` : null],
          ]} />
          {rec.criterion && (
            <p className="muted">{t('caseDetail.modulesTab.criterion')}: {rec.criterion}</p>
          )}
        </div>
      )}
      {rec && unstable && (
        <StatChips items={[
          ['L (mm)', rec.length_mm],
          ['m', rec.stability_m],
        ]} />
      )}
      {!unstable && (
        <PlacementBlock placement={result.placement} envelope={result.beam_envelope} />
      )}
      {(result.assumptions || []).length > 0 && (
        <p className="muted">{t('caseDetail.modulesTab.assumptions')}: {result.assumptions.join('；')}</p>
      )}
      {result.disclaimer && <div className="disclaimer">{result.disclaimer}</div>}
    </div>
  );
}

export function PhaseMatchResult({ result }) {
  const { t, te } = useLanguage();
  if (!result.solutions) return null;
  const matched = result.solutions.filter((s) => s.theta_deg != null);
  return (
    <div className="generated-section">
      {result.summary && <p className="result-summary">{result.summary}</p>}
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
      {/* The principal-plane caveat and "verify the cut with the vendor" line
          are the guard against ordering a mis-cut crystal — always visible. */}
      {result.disclaimer && <div className="disclaimer">{result.disclaimer}</div>}
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

export function LiteratureSearchResult({ result }) {
  const { t } = useLanguage();
  if (!result.papers) return null;
  const downloadBibtex = () => {
    // Client-side .bib assembly: entries were rendered by the backend from
    // real index records, never by a model.
    const blob = new Blob([result.papers.map((p) => p.bibtex).filter(Boolean).join('\n\n')],
      { type: 'text/plain;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = 'laserclaw_references.bib';
    link.click();
    URL.revokeObjectURL(link.href);
  };
  return (
    <div className="generated-section">
      {result.summary && <p className="result-summary">{result.summary}</p>}
      {(result.source_errors || []).map((err) => (
        <div key={err} className="disclaimer">{err}</div>
      ))}
      {result.papers.length > 0 && (
        <button type="button" className="btn btn-secondary no-print" onClick={downloadBibtex}>
          {t('caseDetail.modulesTab.litExportBibtex')}
        </button>
      )}
      {result.papers.map((paper) => (
        <div key={paper.doi || paper.arxiv_id || paper.title} className="source-row">
          <div>
            <strong>
              {paper.url
                ? <a href={paper.url} target="_blank" rel="noreferrer">{paper.title}</a>
                : paper.title}
            </strong>
            <p className="muted">
              {(paper.authors || []).slice(0, 3).join(', ')}
              {(paper.authors || []).length > 3 ? t('caseDetail.modulesTab.litEtAl') : ''}
            </p>
            {paper.abstract && (
              <details>
                <summary className="muted">{t('caseDetail.modulesTab.litAbstract')}</summary>
                <p className="muted">{paper.abstract}</p>
              </details>
            )}
          </div>
          <div className="loan-cell">
            {paper.year && <span className="meta-pill">{paper.year}</span>}
            {paper.venue && <span className="meta-pill">{paper.venue}</span>}
            {paper.cited_by != null && (
              <span className="meta-pill">{t('caseDetail.modulesTab.litCitedBy')} {paper.cited_by}</span>
            )}
            <span className="meta-pill">{paper.source}</span>
            {paper.pdf_url && (
              <a className="meta-pill" href={paper.pdf_url} target="_blank" rel="noreferrer">PDF</a>
            )}
          </div>
        </div>
      ))}
      {result.disclaimer && <div className="disclaimer">{result.disclaimer}</div>}
    </div>
  );
}

export function ModuleResult({ moduleType, result, showComparison = true }) {
  // needs_input AND failed both carry their explanation in `message` — a
  // failed run must show WHY, not just a status badge over an empty card.
  if (!result || result.status === 'needs_input' || result.status === 'failed') {
    if (!result?.message) return null;
    return (
      <div className={result.status === 'failed' ? 'error' : 'disclaimer'}>
        {result.message}
      </div>
    );
  }
  if (moduleType === 'power_curve') return <PowerCurveResult result={result} showComparison={showComparison} />;
  if (moduleType === 'cavity_design') return <CavityDesignResult result={result} />;
  if (moduleType === 'phase_match') return <PhaseMatchResult result={result} />;
  if (moduleType === 'coating_tmm') return <CoatingTmmResult result={result} />;
  if (moduleType === 'component_match') return <ComponentMatchResult result={result} />;
  if (moduleType === 'literature_search') return <LiteratureSearchResult result={result} />;
  return result.summary ? <p className="result-summary">{result.summary}</p> : null;
}

/** Kernel results injected into a generated plan (content.computed_physics).
 *
 * This is the line between "deterministically computed" and "model prose":
 * without it the student cannot tell which numbers were calculated and which
 * were written by the LLM — the core promise of v2.
 */
export function PhysicsFactsBlock({ physics }) {
  const { t } = useLanguage();
  if (!physics) return null;

  if (!physics.available) {
    return (
      <div className="error" style={{ marginBottom: '1rem' }}>
        <strong>⚠ {t('caseDetail.physics.notRun')}</strong>
        <p>{t('caseDetail.physics.notRunHint')}</p>
        {(physics.skipped || []).length > 0 && (
          <p className="muted">{t('caseDetail.physics.skippedTitle')}: {physics.skipped.join('；')}</p>
        )}
      </div>
    );
  }

  const results = physics.results || {};
  const search = results.cavity_design_search;
  const design = results.cavity_design;
  const pm = results.phase_matching;
  const coating = results.coating_check;
  const rec = search?.recommended;

  return (
    <div className="generated-section" style={{ border: '1px solid #2f5d3a', borderRadius: '8px', padding: '0.9rem' }}>
      <div className="generated-card-title">
        <h3>{t('caseDetail.physics.title')}</h3>
        <span className="meta-pill">{(physics.tools_run || []).join(' · ')}</span>
      </div>

      {(physics.skipped || []).length > 0 && (
        <div className="disclaimer">{t('caseDetail.physics.skippedTitle')}: {physics.skipped.join('；')}</div>
      )}

      {search && (
        <div>
          {search.note && <p className="muted">{search.note}</p>}
          {rec && (
            <StatChips items={[
              ['R1', rec.R1], ['R2', rec.R2],
              ['L (mm)', rec.length_mm],
              ['w0 (mm)', rec.waist_w0_mm],
              ['w@crystal (mm)', rec.spot_in_crystal_mm],
              [t('caseDetail.physics.wavelength'), search.wavelength_nm != null ? `${search.wavelength_nm} nm` : null],
              [t('caseDetail.physics.thermalTol'),
                rec.thermal_lens_tolerance_dioptre != null
                  ? `${rec.thermal_lens_tolerance_dioptre} D${rec.thermal_lens_tolerance_min_f_mm ? ` (f≥${rec.thermal_lens_tolerance_min_f_mm}mm)` : ''}`
                  : null],
            ]} />
          )}
          <PlacementBlock placement={rec?.element_placement} envelope={rec?.beam_envelope} />
          {(search.alternatives || []).length > 0 && (
            <details>
              <summary className="muted">{t('caseDetail.physics.alternatives')} ({search.alternatives.length})</summary>
              <table className="mini-table">
                <tbody>
                  {search.alternatives.map((c, i) => (
                    <tr key={i}>
                      <td>{c.R1} + {c.R2}</td>
                      <td className="num">L={c.length_mm} mm</td>
                      <td className="num">w0={c.waist_w0_mm} mm</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          )}
          {search.search_space && (
            <p className="muted">
              {t('caseDetail.physics.searchSpace')}:
              {' '}{search.search_space.geometries_evaluated} {t('caseDetail.physics.evaluated')} ·
              {' '}{search.search_space.stable_configurations_found} {t('caseDetail.physics.stableFound')} ·
              {' '}{t('caseDetail.physics.rocSource')}: {search.search_space.roc_source === 'lab inventory'
                ? t('caseDetail.physics.rocInventory') : t('caseDetail.physics.rocCatalog')}
            </p>
          )}
          {(search.caveats || []).map((c) => <div key={c} className="disclaimer">{c}</div>)}
        </div>
      )}

      {design && (
        <div>
          {design.summary && <p className="result-summary">{design.summary}</p>}
          <StatChips items={[
            ['L (mm)', design.recommended_length_mm],
            ['w0 (mm)', design.waist_w0_mm],
            ['w@M1 (mm)', design.spot_on_mirror1_mm],
            ['w@M2 (mm)', design.spot_on_mirror2_mm],
            ['w@crystal (mm)', design.spot_in_crystal_mm],
          ]} />
          <PlacementBlock placement={design.element_placement} envelope={design.beam_envelope} />
        </div>
      )}

      {pm && Object.entries(pm).map(([stage, entry]) => (
        <div key={stage}>
          <h3>{t('caseDetail.physics.phaseTitle')} — {stage}</h3>
          <table className="mini-table">
            <thead><tr><th>{t('caseDetail.modulesTab.colPlane')}</th><th className="num">θ (°)</th><th className="num">φ (°)</th><th className="num">λ₃ (nm)</th></tr></thead>
            <tbody>
              {(entry.solutions || []).map((s, i) => (
                <tr key={i}>
                  <td>{s.plane || 'uniaxial'}</td>
                  <td className="num">{s.theta_deg}</td>
                  <td className="num">{s.phi_deg ?? '-'}</td>
                  <td className="num">{s.lambda3_nm}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {entry.note && <div className="disclaimer">{entry.note}</div>}
        </div>
      ))}

      {coating && (
        <div>
          <h3>{t('caseDetail.physics.coatingTitle')}</h3>
          {coating.summary && <p className="result-summary">{coating.summary}</p>}
        </div>
      )}

      {/* physics.note is the instruction addressed to the LLM, not to the
          reader — the block title already states these values are computed. */}
    </div>
  );
}
