(() => {
  const original = DASH.renderCycleSignals;
  if (typeof original !== 'function') return;

  DASH.renderCycleSignals = () => {
    original();

    const foreign = DASH.data?.cycle_signals?.foreign || {};
    const metrics = document.getElementById('foreignCycleMetrics');
    const text = document.getElementById('foreignCycleText');
    const f = DASH.f;
    if (!metrics) return;

    const snap = foreign.market_snapshot || {};
    const hasMarketOwnership = snap.kospi_foreign_ownership_mcap_weighted_pct != null;
    const fourthCard = hasMarketOwnership
      ? `<div class="metric"><span class="muted">KOSPI 외국인 보유 비중</span><b>${f(snap.kospi_foreign_ownership_mcap_weighted_pct)}%</b><small>${snap.date || '-'} 확정치</small></div>`
      : `<div class="metric"><span class="muted">최근 5일 외국인 순매수</span><b>${f(foreign.net_buy_5d_trn)}조원</b><small>KOSPI 보유비중 미산출 시 대체</small></div>`;

    metrics.innerHTML = `
      <div class="metric"><span class="muted">최근 20일 순매수</span><b>${f(foreign.net_buy_20d_trn)}조원</b><small>5일 ${f(foreign.net_buy_5d_trn)}조원</small></div>
      <div class="metric"><span class="muted">삼성 외국인 지분율</span><b>${f(foreign.samsung_foreign_ownership_pct)}%</b><small>20일 ${f(foreign.samsung_foreign_ownership_20d_change_pp)}%p</small></div>
      <div class="metric"><span class="muted">하이닉스 외국인 지분율</span><b>${f(foreign.skhynix_foreign_ownership_pct)}%</b><small>20일 ${f(foreign.skhynix_foreign_ownership_20d_change_pp)}%p</small></div>
      ${fourthCard}`;

    if (text) {
      const source = foreign.source || '원자료 미확인';
      const caveat = hasMarketOwnership
        ? `KOSPI 외국인 보유비중은 ${snap.date || '-'} 확정치입니다.`
        : 'KOSPI 전체 외국인 보유비중은 이번 실행에서 얻지 못해 5일 순매수로 대체했습니다.';
      const status = text.querySelector('.status-line');
      if (status) status.innerHTML = `${source}<br>${caveat} 삼성전자·SK하이닉스 지분율은 확정치 시차가 있을 수 있습니다.`;
    }
  };
})();
