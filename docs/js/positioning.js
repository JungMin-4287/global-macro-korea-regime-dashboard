(() => {
  const originalRenderOther = DASH.renderOther;

  const fmt = (value, digits = 1) => {
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString('ko-KR', {maximumFractionDigits: digits}) : '-';
  };

  const directionText = value => {
    const text = String(value || '').toLowerCase();
    if (['up', 'rising', 'positive', '상승', '상향'].includes(text)) return '상향';
    if (['down', 'falling', 'declining', 'negative', '하락', '하향'].includes(text)) return '하향';
    return '확인 대기';
  };

  const scoreClass = score => {
    if (score == null) return 'neutral';
    if (score >= 65) return 'warn';
    if (score < 30) return 'bad';
    if (score < 45) return 'neutral';
    return 'good';
  };

  DASH.renderPositioningAnalysis = () => {
    const target = document.getElementById('positioning');
    if (!target) return;

    const manual = DASH.data?.manual?.positioning || {};
    const analysis = DASH.data?.positioning_analysis || {};
    const inst = analysis.institutional_snapshot || manual.global_memory_ls || {};
    const proxy = analysis.daily_proxy || {};
    const judgement = analysis.combined_judgement || {};
    const components = proxy.components || [];
    const f = DASH.f;

    const institutionBadge = inst.status || '과밀 상당 부분 해소 · 아직 롱 우위';
    const peakText = inst.prior_peak_ratio_min != null ? `${fmt(inst.prior_peak_ratio_min)}배+` : '-';

    const componentRows = components.map(component => {
      const available = component.available && component.score != null;
      return `<div class="position-component ${available ? '' : 'unavailable'}">
        <div><b>${component.name}</b><small>가중치 ${fmt(component.weight, 0)}%</small></div>
        <span>${available ? `${fmt(component.score)}점` : '미산출'}</span>
      </div>`;
    }).join('');

    const missing = (proxy.missing_components || []).join(' · ') || '없음';
    const proxyScore = proxy.score == null ? '-' : fmt(proxy.score);
    const progress = proxy.score == null ? 0 : Math.max(0, Math.min(100, Number(proxy.score)));

    target.innerHTML = `
      <div class="position-section">
        <div class="position-head">
          <div>
            <small class="position-kicker">기관 포지셔닝 · 수동 스냅샷</small>
            <h3>글로벌 메모리 L/S</h3>
          </div>
          <span class="badge warn">${institutionBadge}</span>
        </div>
        <div class="position-metrics">
          <div class="metric"><span class="muted">글로벌 메모리 L/S</span><b>${fmt(inst.ratio)}배</b><small>직전 고점 ${peakText}</small></div>
          <div class="metric"><span class="muted">2020년 이후 백분위</span><b>${fmt(inst.percentile_since_2020)}%</b><small>장기 중간보다 높음</small></div>
          <div class="metric"><span class="muted">최근 12개월 백분위</span><b>${fmt(inst.percentile_12m)}%</b><small>최근 과밀 대비 낮음</small></div>
          <div class="metric"><span class="muted">전체 반도체 L/S</span><b>미국 ${f(manual.us_semiconductor_ls_percentile)}%</b><small>아시아 ${f(manual.asia_supply_chain_ls_percentile)}%</small></div>
        </div>
        <div class="position-callout">
          <b>${judgement.label || '포지션·업황 결합 판정 대기'}</b>
          <p>${judgement.text || '기관 L/S 방향과 DRAM ASP·EPS 방향을 함께 확인합니다.'}</p>
          <div class="position-directions">
            <span>L/S ${directionText(judgement.ls_direction)}</span>
            <span>DRAM ASP ${directionText(judgement.dram_asp_direction)}</span>
            <span>EPS ${directionText(judgement.eps_revision_direction)}</span>
          </div>
        </div>
        <div class="status-line">기준일 ${inst.reference_date || manual.reference_date || '-'} · ${inst.source || manual.source || '-'} · 원자료 비공개, 다음 기관 자료 입수 시 갱신</div>
      </div>

      <div class="position-divider"></div>

      <div class="position-section">
        <div class="position-head proxy-head">
          <div>
            <small class="position-kicker">공개 데이터 · 일일 자동 프록시</small>
            <h3>메모리 포지셔닝 지수</h3>
          </div>
          <span class="badge ${scoreClass(proxy.score)}">${proxyScore}점 · ${proxy.state || '미산출'}</span>
        </div>
        <div class="proxy-bar"><span style="width:${progress}%"></span></div>
        <div class="proxy-coverage">데이터 커버리지 <b>${fmt(proxy.coverage_pct, 0)}%</b> · 기관 L/S 수동값은 이 점수에 미포함</div>
        <div class="position-components">${componentRows || '<div class="status-line">프록시 구성요소 미산출</div>'}</div>
        <div class="note positioning-note">
          ${proxy.note || '확보된 공개 데이터만 사용합니다.'}
          <div class="status-line">미연결 항목: ${missing}</div>
        </div>
      </div>`;
  };

  DASH.renderOther = () => {
    if (typeof originalRenderOther === 'function') originalRenderOther();
    DASH.renderPositioningAnalysis();
  };
})();
