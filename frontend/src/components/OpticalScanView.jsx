import React, { useRef, useState } from 'react';
import ScientificPlot from './ScientificPlot';

export const opticalParameterLabels = {
  length_mm: '长度 / mm', focal_mm: '空气等效焦距 f / mm', radius_mm: '曲率半径 R / mm',
  aoi_deg: '入射角 / °', n: '折射率 n', gradient_per_mm: 'GRIN 梯度 / mm⁻¹',
  front_radius_mm: '前表面曲率 R / mm', back_radius_mm: '后表面曲率 R / mm',
};
const axisName = (axis, system) => {
  const name = system?.elements?.[axis.element_index]?.name || `元件 ${axis.element_index + 1}`;
  return { name, parameter: opticalParameterLabels[axis.parameter] || axis.parameter };
};

export default function OpticalScanView({ scan, system, recordLabel = '' }) {
  const [metric, setMetric] = useState('stable_both'), [error, setError] = useState('');
  const plot = useRef(null);
  const x = axisName(scan.x_axis, system), y = axisName(scan.y_axis, system);
  const binary = metric === 'stable_both';
  const values = scan.maps[metric];
  const stableCount = scan.maps.stable_both.flat().filter(value => value === 1).length;
  const title = binary ? '双轴稳定性' : (metric === 'tangential' ? '切向 T' : '弧矢 S') + ' · m=(A+D)/2';
  const csv = () => {
    const rows = [['x_' + scan.x_axis.parameter, 'y_' + scan.y_axis.parameter, 'm_T', 'm_S', 'stable_both'],
      ...scan.y.flatMap((yValue, row) => scan.x.map((xValue, column) => [xValue, yValue,
        scan.maps.tangential[row][column], scan.maps.sagittal[row][column], scan.maps.stable_both[row][column]]))];
    const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'stability-' + recordLabel + '.csv'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <section className="field-view" aria-label="二维稳定性参数扫描">
    <div className="field-heading"><h3>二维稳定图{recordLabel && ' · ' + recordLabel}</h3></div>
    <p className="field-caption">X：{x.name} · {x.parameter}<br />Y：{y.name} · {y.parameter}</p>
    <div className="field-toolbar"><label>颜色表示<select aria-label="稳定图颜色指标" value={metric} onChange={event => setMetric(event.target.value)}>
      <option value="stable_both">双轴稳定 / 非双轴稳定</option><option value="tangential">切向 T 稳定参数 m</option><option value="sagittal">弧矢 S 稳定参数 m</option>
    </select></label><div className="field-export"><button onClick={csv}>导出扫描 CSV</button>{['svg', 'png'].map(format => <button key={format} onClick={() => plot.current?.exportImage(format).catch(e => setError(e.message))}>{format.toUpperCase()}</button>)}</div></div>
    {error && <p role="alert" className="wb-error">{error}</p>}
    <ScientificPlot ref={plot} data={[{ type: 'heatmap', x: scan.x, y: scan.y, z: values,
      zmin: binary ? 0 : -1, zmax: 1,
      colorscale: binary ? [[0, '#664452'], [.499, '#664452'], [.5, '#68bda8'], [1, '#68bda8']] : [[0, '#9876c7'], [.5, '#e2eedc'], [1, '#cf8b5f']],
      colorbar: { title: { text: binary ? '' : 'm' }, tickvals: binary ? [0, 1] : [-1, 0, 1],
        ...(binary ? { ticktext: ['非双轴稳定', '双轴稳定'] } : {}), thickness: 14 },
      hoverongaps: false,
      hovertemplate: x.parameter + ' = %{x:.4f}<br>' + y.parameter + ' = %{y:.4f}<br>' + title + ' = %{z:.5g}<extra></extra>',
    }]} layout={{ title: { text: title + (recordLabel ? ' · ' + recordLabel : ''), x: .04, font: { size: 14 } },
      height: 450, autosize: true, margin: { l: 110, r: 115, t: 50, b: 90 },
      paper_bgcolor: '#111c28', plot_bgcolor: '#111c28', font: { color: '#d6e2ef', size: 12 },
      xaxis: { title: { text: 'X · ' + x.name.slice(0, 24) + '<br>' + x.parameter, standoff: 14 }, zeroline: false },
      yaxis: { title: { text: 'Y · ' + y.name.slice(0, 24) + '<br>' + y.parameter, standoff: 14 }, zeroline: false }, hovermode: 'closest',
      uirevision: recordLabel + ':' + metric,
    }} filename={'stability-' + recordLabel} />
    <p className="field-caption">共{scan.grid_points}点，双轴稳定{stableCount}点，无效{scan.invalid_count}点（空白）。|m|&lt;1为稳定；m=±1为临界。连续色图超出±1的数值在端点颜色截断，悬停查看原值。</p>
    <p className="field-note">这是离散参数网格的几何稳定性。空气等效薄透镜焦距与介质内物理焦距需按模型换算；图中不包含输出功率、热负载或效率排名。</p>
  </section>;
}
