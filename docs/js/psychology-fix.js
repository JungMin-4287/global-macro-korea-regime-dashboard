(() => {
  const shortDate = value => {
    const text = String(value || '');
    const m = text.match(/(?:\d{4}-)?(\d{1,2})-(\d{1,2})$/);
    return m ? `${Number(m[1])}/${Number(m[2])}` : text;
  };

  const finite = value => Number.isFinite(Number(value));

  DASH.renderPsychology = p => {
    DASH.renderCorrectionFlow(p.correction_map || {});

    const e = document.getElementById('psychology');
    const metrics = document.getElementById('psychologyMetrics');
    const text = document.getElementById('psychologyText');
    const points = p.points || [];
    const highlights = p.highlights || [];
    const f = DASH.f;
    const C = DASH.C;

    if (!e || !metrics || !text) return;
    if (!points.length) {
      e.parentElement.innerHTML = '<div class="note bad-note"><b>수급 데이터 미산출</b><br>KRX와 네이버 금융을 순차 조회했지만 가격 데이터와 결합할 수 있는 개인 순매수 시계열을 받지 못했습니다.</div>';
      metrics.innerHTML = '<div class="metric"><span class="muted">현재 구간</span><b>미산출</b></div><div class="metric"><span class="muted">개인 순매수</span><b>-</b></div><div class="metric"><span class="muted">KOSPI 수익률</span><b>-</b></div><div class="metric"><span class="muted">과거 패턴 대비</span><b>-</b></div>';
      text.innerHTML = `<div class="headline">현재 판단을 만들 수 없습니다.</div><div>${p.interpretation || '개인 순매수 데이터 미산출'}</div><div class="status-line">${p.source || p.error || '다음 자동 실행에서 재시도합니다.'}</div>`;
      return;
    }

    const scatter = points
      .map(d => ({x: Number(d.y), y: Number(d.x), date: d.date}))
      .filter(d => finite(d.x) && finite(d.y));
    const fit = DASH.linearFit(scatter);
    const latestRaw = p.latest || {};
    const latestDate = latestRaw.date || scatter.at(-1)?.date;
    const recent = scatter.length ? [{...scatter.at(-1), label: shortDate(latestDate)}] : [];
    const marked = highlights
      .map(d => ({x: Number(d.y), y: Number(d.x), label: shortDate(d.label || d.date), date: d.date}))
      .filter(d => finite(d.x) && finite(d.y) && d.date !== latestDate)
      .slice(0, 6);

    const xAbs = Math.max(10, Math.ceil(Math.max(...scatter.map(d => Math.abs(d.x)), ...marked.map(d => Math.abs(d.x)), 0) * 1.12));
    const yAbs = Math.max(6, Math.ceil(Math.max(...scatter.map(d => Math.abs(d.y)), ...marked.map(d => Math.abs(d.y)), 0) * 1.15));

    const zones = {
      id: 'sentimentZonesCentered',
      beforeDatasetsDraw(chart) {
        const {ctx, chartArea, scales} = chart;
        if (!chartArea || !scales.x || !scales.y) return;
        const {left, right, top, bottom} = chartArea;
        const x0 = scales.x.getPixelForValue(0);
        const y0 = scales.y.getPixelForValue(0);
        ctx.save();
        ctx.fillStyle = 'rgba(255,150,80,.10)';
        ctx.fillRect(x0, top, right - x0, y0 - top);
        ctx.fillStyle = 'rgba(255,220,90,.09)';
        ctx.fillRect(left, y0, x0 - left, bottom - y0);
        ctx.fillStyle = 'rgba(111,168,255,.045)';
        ctx.fillRect(left, top, x0 - left, y0 - top);
        ctx.fillRect(x0, y0, right - x0, bottom - y0);

        ctx.font = '700 13px system-ui';
        ctx.fillStyle = '#ffbd4a';
        const greed = '탐욕·추격 관찰';
        const fear = '공포·투매 관찰';
        ctx.fillText(greed, right - ctx.measureText(greed).width - 12, top + 21);
        ctx.fillText(fear, left + 12, bottom - 12);
        ctx.restore();
      }
    };

    const labelsInside = {
      id: 'sentimentLabelsInside',
      afterDatasetsDraw(chart) {
        const {ctx, chartArea} = chart;
        const datasets = [
          {index: 2, color: '#ffbd4a'},
          {index: 3, color: '#ff9d3f'}
        ];
        ctx.save();
        ctx.font = '700 12px system-ui';
        ctx.lineWidth = 4;
        ctx.strokeStyle = 'rgba(8,16,31,.96)';

        datasets.forEach(({index, color}) => {
          const meta = chart.getDatasetMeta(index);
          const rows = chart.data.datasets[index]?.data || [];
          meta.data.forEach((pt, i) => {
            const label = rows[i]?.label;
            if (!label) return;
            const width = ctx.measureText(label).width;
            let x = pt.x + 9;
            let y = pt.y - 9;
            if (pt.x > chartArea.right - width - 18) x = pt.x - width - 9;
            if (pt.x < chartArea.left + 18) x = pt.x + 9;
            if (pt.y < chartArea.top + 18) y = pt.y + 17;
            if (pt.y > chartArea.bottom - 12) y = pt.y - 11;
            x = Math.max(chartArea.left + 4, Math.min(x, chartArea.right - width - 4));
            y = Math.max(chartArea.top + 13, Math.min(y, chartArea.bottom - 4));
            ctx.fillStyle = color;
            ctx.strokeText(label, x, y);
            ctx.fillText(label, x, y);
          });
        });
        ctx.restore();
      }
    };

    new Chart(e, {
      type: 'scatter',
      data: {datasets: [
        {label: '일별 관측치', data: scatter, backgroundColor: 'rgba(160,180,205,.68)', borderColor: 'rgba(110,130,155,.85)', pointRadius: 3.2, pointHoverRadius: 5, clip: 8},
        {label: '평소 수급 패턴', type: 'line', data: fit, borderColor: C.a, borderDash: [6,5], borderWidth: 2, pointRadius: 0, clip: 8},
        {label: '최근', data: recent, backgroundColor: C.w, borderColor: '#9b6b00', borderWidth: 2, pointRadius: 8, pointHoverRadius: 9, clip: 12},
        {label: '주요 변곡', data: marked, backgroundColor: '#ff9d3f', borderColor: '#4b2a00', borderWidth: 2, pointRadius: 7, pointHoverRadius: 8, clip: 12}
      ]},
      plugins: [zones, labelsInside],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        layout: {padding: {top: 18, right: 28, bottom: 10, left: 12}},
        interaction: {mode: 'nearest', intersect: false},
        plugins: {
          legend: {labels: {color: '#c8d2e8', boxWidth: 18}},
          tooltip: {callbacks: {label: ctx => {
            const d = ctx.raw || {};
            return `${d.date || ctx.dataset.label}: KOSPI ${f(d.x)}% · 개인 ${f(d.y)}조원`;
          }}}
        },
        scales: {
          x: {
            min: -xAbs,
            max: xAbs,
            title: {display: true, text: 'KOSPI 수익률(%)', color: '#95a3bd'},
            ticks: {color: '#95a3bd', maxTicksLimit: 9},
            grid: {color: ctx => Number(ctx.tick.value) === 0 ? 'rgba(238,244,255,.45)' : 'rgba(43,59,94,.3)', lineWidth: ctx => Number(ctx.tick.value) === 0 ? 1.5 : 1}
          },
          y: {
            min: -yAbs,
            max: yAbs,
            title: {display: true, text: '개인 순매수(조원)', color: '#95a3bd'},
            ticks: {color: '#95a3bd', maxTicksLimit: 9},
            grid: {color: ctx => Number(ctx.tick.value) === 0 ? 'rgba(238,244,255,.45)' : 'rgba(43,59,94,.3)', lineWidth: ctx => Number(ctx.tick.value) === 0 ? 1.5 : 1}
          }
        }
      }
    });

    const z = p.latest || {};
    const ret = Number(z.y), buy = Number(z.x), res = Number(z.residual);
    let zone = '중립 수급', meaning = '개인 수급과 지수 움직임이 평소 범위에 있습니다.', action = '추가 방향 확인이 필요합니다.';
    if (ret < 0 && buy < 0) {
      zone = '공포·투매 후보';
      meaning = '지수가 하락하는데 개인도 함께 팔았습니다. 평소의 저가매수 행동마저 약해진 강한 공포 구간입니다.';
      action = '매도 고갈 후보이지만 다음 거래일 저점 방어와 VKOSPI 하락 전환 전에는 매수 신호로 보지 않습니다.';
    } else if (ret > 0 && buy > 0) {
      zone = '탐욕·추격 후보';
      meaning = '지수가 오르는 날 개인도 순매수했습니다. 상승을 뒤늦게 따라붙는 추격매수일 수 있습니다.';
      action = '추세가 이어질 수 있으나 이격도 확대와 거래대금 급증이 겹치면 신규 추격매수를 줄입니다.';
    } else if (ret < 0 && buy > 0) {
      zone = '개인 저가매수·지수 하락';
      meaning = '개인이 외국인·기관 매물을 받아냈지만 지수는 하락했습니다. 매도 압력이 개인 매수보다 강한 상태입니다.';
      action = '청산이 끝났다고 보기 어렵습니다. 외국인 수급 반전과 종가 회복을 확인합니다.';
    } else if (ret > 0 && buy < 0) {
      zone = '외국인·기관 주도 상승';
      meaning = '개인이 파는데도 지수가 올랐습니다. 외국인·기관이 가격을 끌어올리는 비교적 건전한 수급입니다.';
      action = '시장 폭까지 개선되면 반등 신뢰도를 높입니다.';
    }
    const residualText = finite(res)
      ? (res < -1 ? '과거 관계보다 지수 반응이 더 약합니다.' : res > 1 ? '과거 관계보다 지수 반응이 더 강합니다.' : '과거 수급 관계에서 크게 벗어나지 않았습니다.')
      : '회귀 잔차는 미산출입니다.';

    metrics.innerHTML = `<div class="metric"><span class="muted">현재 구간</span><b>${zone}</b></div><div class="metric"><span class="muted">개인 순매수</span><b>${f(buy)}조원</b></div><div class="metric"><span class="muted">KOSPI 수익률</span><b>${f(ret)}%</b></div><div class="metric"><span class="muted">과거 패턴 대비</span><b>${f(res)}%p</b></div>`;
    text.innerHTML = `<div class="headline">오늘 위치: ${zone}</div><div><b>무슨 뜻?</b> ${meaning} ${residualText}</div><div class="action"><b>투자 판단:</b> ${action}</div><div class="status-line">상관계수 ${f(p.correlation)} · 기준일 ${z.date || '-'} · ${p.source || '-'}<br>${p.highlight_note || ''}</div>`;
  };
})();
