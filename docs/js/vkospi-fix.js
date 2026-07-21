(() => {
  const originalRenderEnv = DASH.renderEnv;

  const finiteOrNull = value => {
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };

  const rollingMean = (values, window) => values.map((_, index) => {
    if (index + 1 < window) return null;
    const sample = values.slice(index - window + 1, index + 1);
    if (sample.length !== window || sample.some(value => value === null)) return null;
    return sample.reduce((sum, value) => sum + value, 0) / window;
  });

  const lastFinite = values => {
    for (let index = values.length - 1; index >= 0; index -= 1) {
      if (Number.isFinite(values[index])) return values[index];
    }
    return null;
  };

  const displayAverage = (value, count, required, formatter) =>
    count < required || !Number.isFinite(value) ? '데이터 부족' : formatter(value);

  DASH.renderEnv = () => {
    originalRenderEnv();

    const v = DASH.data?.assets?.VKOSPI;
    const canvas = document.getElementById('VKOSPI-price');
    const metrics = document.getElementById('vkospiMetrics');
    const text = document.getElementById('vkospiText');
    if (!v || !canvas) return;

    const rows = (v.history || [])
      .map(row => ({ date: row.date, close: finiteOrNull(row.close) }))
      .filter(row => row.date && row.close !== null)
      .slice(-260);
    if (!rows.length) return;

    const labels = rows.map(row => row.date);
    const closes = rows.map(row => row.close);
    const sma20 = rollingMean(closes, 20);
    const sma50 = rollingMean(closes, 50);
    const sma20Last = lastFinite(sma20);
    const sma50Last = lastFinite(sma50);
    const level = finiteOrNull(v.close) ?? closes[closes.length - 1];
    const dailyMove = Number.isFinite(level) ? level / Math.sqrt(252) : null;
    const recentHigh = Math.max(...closes.slice(-20));
    const offHigh = Number.isFinite(level) && Number.isFinite(recentHigh) && recentHigh !== 0
      ? (level / recentHigh - 1) * 100
      : null;
    const f = DASH.f;
    const C = DASH.C;

    if (metrics) {
      metrics.innerHTML = `
        <div class="metric"><span class="muted">현재 VKOSPI</span><b>${f(level)}</b></div>
        <div class="metric"><span class="muted">하루 예상 변동폭</span><b>±${f(dailyMove)}%</b><small>연환산값 단순 환산</small></div>
        <div class="metric"><span class="muted">20일 평균</span><b>${displayAverage(sma20Last, closes.length, 20, f)}</b><small>${closes.length}/20일 확보</small></div>
        <div class="metric"><span class="muted">20일 고점 대비</span><b>${f(offHigh)}%</b></div>`;
    }

    const oldChart = Chart.getChart(canvas);
    if (oldChart) oldChart.destroy();

    const datasets = [{
      label: v.is_proxy ? 'KOSPI 20일 실현변동성(대체)' : 'VKOSPI',
      data: closes,
      borderColor: C.r,
      backgroundColor: 'rgba(255,101,119,.12)',
      fill: true,
      pointRadius: rows.length < 3 ? 7 : rows.length < 15 ? 3 : 0,
      borderWidth: 3,
      spanGaps: false,
      tension: .18,
    }];
    if (sma20Last !== null) {
      datasets.push({
        label: '20일 평균',
        data: sma20,
        borderColor: C.w,
        pointRadius: 0,
        borderWidth: 1.7,
        spanGaps: false,
      });
    }
    if (sma50Last !== null) {
      datasets.push({
        label: '50일 평균',
        data: sma50,
        borderColor: C.a,
        pointRadius: 0,
        borderWidth: 1.7,
        spanGaps: false,
      });
    }

    const allVisible = [...closes, ...sma20, ...sma50].filter(Number.isFinite);
    const min = Math.min(...allVisible);
    const max = Math.max(...allVisible);
    const pad = Math.max(2, (max - min) * .12);

    new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { labels: { color: '#c8d2e8', boxWidth: 18 } },
          tooltip: {
            callbacks: {
              label: context => context.parsed.y === null
                ? `${context.dataset.label}: 데이터 부족`
                : `${context.dataset.label}: ${f(context.parsed.y)}`,
            },
          },
        },
        scales: {
          x: {
            ticks: { color: '#95a3bd', maxTicksLimit: 7 },
            grid: { color: 'rgba(43,59,94,.25)' },
          },
          y: {
            suggestedMin: min - pad,
            suggestedMax: max + pad,
            ticks: { color: '#95a3bd' },
            grid: { color: 'rgba(43,59,94,.3)' },
          },
        },
      },
    });

    if (text) {
      const status = text.querySelector('.status-line');
      if (status) {
        status.innerHTML = `20일 평균 ${displayAverage(sma20Last, closes.length, 20, f)} · 50일 평균 ${displayAverage(sma50Last, closes.length, 50, f)} · 유효 이력 ${closes.length}일 · ${v.source || '-'} · 기준일 ${v.date || '-'}`;
      }
    }
  };
})();
