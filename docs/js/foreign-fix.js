(() => {
  const originalCycle = DASH.renderCycleSignals;
  if (typeof originalCycle === 'function') {
    DASH.renderCycleSignals = () => {
      originalCycle();

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
  }

  DASH.renderErrors = () => {
    const box = document.getElementById('errors');
    if (!box) return;
    const raw = [
      ...Object.entries(DASH.data?.errors || {}).map(([key, value]) => ({key, value: String(value)})),
      ...((DASH.data?.cycle_signals?.errors || []).map((value, i) => ({key: `cycle_${i + 1}`, value: String(value)})))
    ];
    if (!raw.length) {
      box.innerHTML = '모든 핵심 데이터가 정상 수집됐습니다.';
      return;
    }
    const translated = raw.map(({key, value}) => {
      const lower = value.toLowerCase();
      if (lower.includes('market snapshot') || lower.includes('are in the [columns]')) {
        return '<div><b>KOSPI 시장 스냅샷 일부 미산출</b>: KRX가 상장주식수·외국인보유주식수 열을 제공하지 않아 KOSPI 전체 외국인 보유비중만 계산하지 못했습니다. 시가총액, 외국인 순매수, 삼성전자·SK하이닉스 지분율은 별도로 표시됩니다.</div>';
      }
      if (lower.includes('foreign flow')) {
        return '<div><b>외국인 순매수 수집 지연</b>: KRX·네이버 일별 자료를 받지 못했습니다. 이전 정상 CSV를 사용하거나 다음 실행에서 다시 조회합니다.</div>';
      }
      if (lower.includes('ownership')) {
        return '<div><b>종목별 외국인 지분율 수집 지연</b>: 해당 종목의 최신 확정 보유율을 받지 못했습니다.</div>';
      }
      return `<div><b>${key}</b>: 일부 보조 데이터 수집에 실패했습니다. 상세 원문은 GitHub의 market_data.json에 보존됩니다.</div>`;
    });
    box.innerHTML = [...new Set(translated)].join('');
  };
})();
