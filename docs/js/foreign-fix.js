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

      const multi = foreign.market_flow_multi_horizon || {};
      const horizon = multi.net_buy_trn || {};
      const ownership = foreign.ownership_multi_horizon || {};
      const sam = ownership.samsung || {};
      const hyn = ownership.skhynix || {};
      const samChg = sam.change_pp || {};
      const hynChg = hyn.change_pp || {};
      const snap = foreign.market_snapshot || {};

      metrics.innerHTML = `
        <div class="metric"><span class="muted">KOSPI 외국인 순매수</span><b>1일 ${f(horizon['1'])}조원</b><small>5일 ${f(horizon['5'])} · 20일 ${f(horizon['20'])}</small></div>
        <div class="metric"><span class="muted">수급 속도</span><b>${multi.reversal_state || '-'}</b><small>5일 가속도 ${f(multi.acceleration_5d_trn)}조원 · ${multi.streak_days || 0}일 ${multi.streak_direction || '중립'}</small></div>
        <div class="metric"><span class="muted">삼성 외국인 지분율</span><b>${f(sam.current_pct ?? foreign.samsung_foreign_ownership_pct)}%</b><small>5일 ${f(samChg['5'])}%p · 20일 ${f(samChg['20'])}%p</small></div>
        <div class="metric"><span class="muted">하이닉스 외국인 지분율</span><b>${f(hyn.current_pct ?? foreign.skhynix_foreign_ownership_pct)}%</b><small>5일 ${f(hynChg['5'])}%p · 20일 ${f(hynChg['20'])}%p</small></div>`;

      if (text) {
        const gate = foreign.multi_horizon_gate || {};
        const signal = gate.signal || foreign.signal || '데이터 축적 중';
        const source = multi.source || foreign.source || '원자료 미확인';
        const judgement = signal === '수급 회복 확인'
          ? '단기 순매수 반전과 20일 지속성, 종목별 지분율 회복이 함께 확인됐습니다.'
          : signal === '단기 반전 진행'
            ? '1일·5일 수급은 개선 중이지만 20일 누적과 두 종목 지분율이 모두 돌아섰는지 추가 확인이 필요합니다.'
            : '단기와 중기 수급이 동시에 약해 외국인 매도 압력이 끝났다고 보기 어렵습니다.';
        text.innerHTML = `<div class="headline">현재 판단: ${signal}</div><div><b>무슨 뜻?</b> ${judgement}</div><div class="action"><b>판정 기준:</b> 1·5·10·20·60일 순매수, 5일 가속도, 삼성전자·SK하이닉스 외국인 지분율 변화를 함께 봅니다.</div><div class="status-line">${source} · 기준일 ${multi.latest_date || '-'} · 관측치 ${multi.observation_count || 0}일<br>KOSPI 전체 외국인 보유비중은 원자료 열이 없을 때 미산출하며, 단기 순매수와 종목별 지분율로 대체 판단합니다.</div>`;
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
