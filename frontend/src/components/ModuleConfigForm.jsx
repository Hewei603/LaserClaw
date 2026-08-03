import React from 'react';
import { useLanguage } from '../LanguageContext';

// Per-module-type field specs. The form stores raw input STRINGS; all number
// parsing and JSON nesting happens in buildModuleConfig, so a half-typed value
// can never crash the form. Empty fields are simply omitted — the backend then
// falls back to the case's experiment parameters (module run merges
// {...case.parameters, ...config_json}).
const FIELD_SPECS = {
  cavity_design: [
    { key: 'wavelength_nm', kind: 'number', label: 'waveL', placeholder: '1064' },
    { key: 'R1_mm', kind: 'rocText', label: 'r1', placeholder: 'flat' },
    { key: 'R2_mm', kind: 'rocText', label: 'r2', placeholder: '300' },
    { key: 'L_start', kind: 'number', label: 'lStart', placeholder: '40' },
    { key: 'L_stop', kind: 'number', label: 'lStop', placeholder: '300' },
    { key: 'L_step', kind: 'number', label: 'lStep', placeholder: '5' },
    { key: 'target_waist_mm', kind: 'number', label: 'targetWaist', placeholder: '0.25' },
    { key: 'crystal_n', kind: 'number', label: 'crystalN', placeholder: '1.8147' },
    { key: 'crystal_thickness_mm', kind: 'number', label: 'crystalT', placeholder: '10' },
    { key: 'crystal_position_mm', kind: 'number', label: 'crystalPos', placeholder: '20' },
  ],
  phase_match: [
    { key: 'crystal', kind: 'select', label: 'pmCrystal', options: ['lbo', 'bbo', 'ktp', 'bibo'] },
    { key: 'lambda1_nm', kind: 'number', label: 'lambda1', placeholder: '1064' },
    { key: 'lambda2_nm', kind: 'number', label: 'lambda2', placeholder: '' },
    { key: 'pm_type', kind: 'select', label: 'pmType', options: ['I', 'II'] },
  ],
  coating_tmm: [
    { key: 'nominal_function', kind: 'select', label: 'coatFunction', options: ['HR', 'AR', 'PR'] },
    { key: 'nominal_wavelength_nm', kind: 'number', label: 'coatDesignWl', placeholder: '1123' },
    { key: 'query_wavelengths', kind: 'text', label: 'coatQuery', placeholder: '1064, 808' },
    { key: 'aoi_deg', kind: 'number', label: 'coatAoi', placeholder: '0' },
  ],
  power_curve: [
    { key: 'output_coupler_T_pct', kind: 'number', label: 'ocT', placeholder: '5' },
    { key: 'label', kind: 'text', label: 'seriesLabel', placeholder: 'T=5%' },
  ],
  stability: [
    { key: 'roi', kind: 'text', label: 'roi', placeholder: '100,200,300,80' },
  ],
};

const HINT_KEYS = {
  cavity_design: 'hintCavity',
  phase_match: 'hintPhase',
  coating_tmm: 'hintCoating',
  power_curve: 'hintPower',
  stability: 'hintStability',
};

const FLAT_WORDS = ['flat', 'inf', 'infinite', 'plane', '平', '平镜', '平面', '无限'];

// Laser students write numbers with units ("300mm", "1064 nm", "5°"). Strip a
// trailing unit, then require the rest to be a plain number — anything else is
// a hard parse error surfaced to the user, never a silent drop.
const parseNumber = (raw) => {
  const text = (raw || '').trim().replace(/(mm|nm|um|μm|deg|度|°|%)\s*$/i, '').trim();
  if (!text) return { empty: true };
  if (!/^[-+]?(\d+\.?\d*|\.\d+)$/.test(text)) return { error: true };
  return { value: Number(text) };
};

// Raw form strings -> { config, errors } where errors lists the i18n label
// keys of fields whose content could not be understood. Callers must refuse to
// run when errors is non-empty — running with a silently-dropped field means
// computing with parameters the user never intended.
export function buildModuleConfig(moduleType, values = {}) {
  const config = {};
  const errors = [];

  const num = (fieldKey, labelKey) => {
    const parsed = parseNumber(values[fieldKey]);
    if (parsed.error) errors.push(labelKey);
    return parsed.value ?? null;
  };

  if (moduleType === 'cavity_design') {
    const wl = num('wavelength_nm', 'waveL');
    if (wl !== null) config.wavelength_nm = wl;
    for (const [key, labelKey] of [['R1_mm', 'r1'], ['R2_mm', 'r2']]) {
      const raw = (values[key] || '').trim().toLowerCase();
      if (!raw) continue;
      if (FLAT_WORDS.includes(raw)) {
        config[key] = 'flat';
      } else {
        const parsed = parseNumber(raw);
        if (parsed.value !== undefined) config[key] = parsed.value;
        else errors.push(labelKey);
      }
    }
    const start = num('L_start', 'lStart');
    const stop = num('L_stop', 'lStop');
    const step = num('L_step', 'lStep');
    if (start !== null && stop !== null) {
      config.L_scan_mm = { start, stop, ...(step !== null ? { step } : {}) };
    }
    const waist = num('target_waist_mm', 'targetWaist');
    if (waist !== null) config.target_waist_mm = waist;
    const n = num('crystal_n', 'crystalN');
    const thickness = num('crystal_thickness_mm', 'crystalT');
    if (n !== null && thickness !== null) {
      config.crystal = { n, thickness_mm: thickness };
      const pos = num('crystal_position_mm', 'crystalPos');
      if (pos !== null) config.crystal.position_mm = pos;
    }
  } else if (moduleType === 'phase_match') {
    if (values.crystal) config.crystal = values.crystal;
    const l1 = num('lambda1_nm', 'lambda1');
    if (l1 !== null) config.lambda1_nm = l1;
    const l2 = num('lambda2_nm', 'lambda2');
    if (l2 !== null) config.lambda2_nm = l2;
    if (values.pm_type) config.pm_type = values.pm_type;
  } else if (moduleType === 'coating_tmm') {
    const design = num('nominal_wavelength_nm', 'coatDesignWl');
    if (design !== null) {
      config.nominal = { design_wavelength_nm: design, function: values.nominal_function || 'HR' };
    }
    const rawQuery = (values.query_wavelengths || '').trim();
    if (rawQuery) {
      const query = rawQuery.split(/[,，、\s]+/).filter(Boolean).map((w) => parseNumber(w));
      if (query.some((q) => q.error)) errors.push('coatQuery');
      else config.query_wavelengths_nm = query.map((q) => q.value);
    }
    const aoi = num('aoi_deg', 'coatAoi');
    if (aoi !== null) config.aoi_deg = aoi;
  } else if (moduleType === 'power_curve') {
    const oc = num('output_coupler_T_pct', 'ocT');
    if (oc !== null) config.output_coupler_T_pct = oc;
    if ((values.label || '').trim()) config.label = values.label.trim();
  } else if (moduleType === 'stability') {
    if ((values.roi || '').trim()) config.roi = values.roi.trim();
  }
  return { config, errors };
}

// Inverse of buildModuleConfig: persisted config_json -> form strings, so the
// form always DISPLAYS what will actually run (the run endpoint persists the
// last effective config). Unknown/extra keys stay invisible here but survive
// in the advanced-JSON path.
export function configToFormValues(moduleType, config = {}) {
  const values = {};
  const put = (key, v) => {
    if (v !== undefined && v !== null) values[key] = String(v);
  };
  if (moduleType === 'cavity_design') {
    put('wavelength_nm', config.wavelength_nm);
    put('R1_mm', config.R1_mm);
    put('R2_mm', config.R2_mm);
    const scan = config.L_scan_mm || {};
    put('L_start', scan.start);
    put('L_stop', scan.stop);
    put('L_step', scan.step);
    put('target_waist_mm', config.target_waist_mm);
    const crystal = (typeof config.crystal === 'object' && config.crystal) || {};
    put('crystal_n', crystal.n);
    put('crystal_thickness_mm', crystal.thickness_mm);
    put('crystal_position_mm', crystal.position_mm);
  } else if (moduleType === 'phase_match') {
    if (typeof config.crystal === 'string') put('crystal', config.crystal);
    put('lambda1_nm', config.lambda1_nm);
    put('lambda2_nm', config.lambda2_nm);
    put('pm_type', config.pm_type);
  } else if (moduleType === 'coating_tmm') {
    const nominal = config.nominal || {};
    put('nominal_function', nominal.function);
    put('nominal_wavelength_nm', nominal.design_wavelength_nm);
    if (Array.isArray(config.query_wavelengths_nm)) {
      values.query_wavelengths = config.query_wavelengths_nm.join(', ');
    }
    put('aoi_deg', config.aoi_deg);
  } else if (moduleType === 'power_curve') {
    put('output_coupler_T_pct', config.output_coupler_T_pct);
    put('label', config.label);
  } else if (moduleType === 'stability') {
    put('roi', config.roi);
  }
  return values;
}

export default function ModuleConfigForm({ moduleType, values, onChange }) {
  const { t } = useLanguage();
  const spec = FIELD_SPECS[moduleType];
  if (!spec) return null;
  return (
    <div className="module-config-form">
      {HINT_KEYS[moduleType] && (
        <p className="muted">{t(`caseDetail.modulesTab.form.${HINT_KEYS[moduleType]}`)}</p>
      )}
      <div className="input-row" style={{ flexWrap: 'wrap' }}>
        {spec.map((field) => (
          <label key={field.key}>
            {t(`caseDetail.modulesTab.form.${field.label}`)}
            {field.kind === 'select' ? (
              <select value={values[field.key] || ''} onChange={(e) => onChange(field.key, e.target.value)}>
                <option value="">{t('caseDetail.modulesTab.form.keepDefault')}</option>
                {field.options.map((opt) => <option key={opt} value={opt}>{opt.toUpperCase()}</option>)}
              </select>
            ) : (
              <input
                value={values[field.key] || ''}
                onChange={(e) => onChange(field.key, e.target.value)}
                placeholder={field.placeholder}
                inputMode={field.kind === 'number' ? 'decimal' : undefined}
              />
            )}
          </label>
        ))}
      </div>
    </div>
  );
}
