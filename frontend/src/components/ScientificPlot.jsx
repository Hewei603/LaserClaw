import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';

let library;
const loadPlotly = () => library ||= import('plotly.js-cartesian-dist-min').then(module => module.default);

// The Cartesian bundle (including 2D heatmaps) is loaded only when an optical design is opened.
const ScientificPlot = forwardRef(function ScientificPlot({ data, layout, onPoint, filename }, ref) {
  const host = useRef(null);
  const plotly = useRef(null);
  const callback = useRef(onPoint);
  const [error, setError] = useState('');
  callback.current = onPoint;
  useImperativeHandle(ref, () => ({
    async exportImage(format) {
      if (!plotly.current || !host.current?._fullLayout) throw new Error('图表尚未加载完成，请稍后导出。');
      await plotly.current.downloadImage(host.current, { format, filename, width: 1600, height: 850, scale: 2 });
    },
  }), [filename]);
  useEffect(() => {
    const element = host.current;
    let alive = true;
    loadPlotly().then(async Plotly => {
      if (!alive) return;
      plotly.current = Plotly;
      await Plotly.react(element, data, layout, {
        responsive: true, displaylogo: false, scrollZoom: false,
        displayModeBar: true, doubleClick: 'reset',
        modeBarButtonsToRemove: ['select2d', 'lasso2d', 'toImage'],
        edits: {},
      });
      if (!alive) return;
      setError('');
      element.removeAllListeners('plotly_click');
      element.on('plotly_click', event => callback.current?.(event.points?.[0]?.x));
    }).catch(err => { if (alive) setError(`绘图加载失败：${err.message}`); });
    return () => { alive = false; };
  }, [data, layout]);
  useEffect(() => {
    const element = host.current;
    const observer = new ResizeObserver(() => {
      if (element._fullLayout && element.clientWidth) plotly.current?.Plots.resize(element);
    });
    observer.observe(element);
    return () => { observer.disconnect(); plotly.current?.purge(element); };
  }, []);
  return <div className="oa-plot-host">{error && <p role="alert">{error}</p>}<div ref={host} className="oa-plot" role="img" aria-label={onPoint ? '可缩放光学分析图，点击曲线选择精确游标位置' : '可缩放光学分析图'} /></div>;
});

export default ScientificPlot;
