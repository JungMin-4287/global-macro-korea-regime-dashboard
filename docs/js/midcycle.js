(() => {
  const icon = item => item.confirmed ? '✓' : item.partial ? '△' : '×';
  const stateClass = item => item.confirmed ? 'confirmed' : item.partial ? 'partial' : 'missing';

  DASH.renderMidCycleClock = () => {
    const x = DASH.data?.mid_cycle_clock;
    const anchor = document.getElementById('SOX-interpretation');
    if (!anchor) return;

    let box = document.getElementById('midCycleClock');
    if (!box) {
      box = document.createElement('div');
      box.id = 'midCycleClock';
      box.className = 'midcycle-clock';
      anchor.insertAdjacentElement('afterend', box);
    }

    if (!x?.available) {
      box.innerHTML = '<div class="midcycle-head"><div><small>Evercore 미드사이클 시계</small><h3>미산출</h3></div></div><p>SOX 종가 이력을 받지 못했습니다.</p>';
      return;
    }

    const f = DASH.f;
    const conditions = (x.conditions || []).map(item => `
      <div class="midcycle-condition ${stateClass(item)}">
        <span class="midcycle-icon">${icon(item)}</span>
        <div><b>${item.name}</b><small>${item.text}</small></div>
      </div>`).join('');

    const badgeClass = x.score >= 3 ? 'good' : x.score >= 2 ? 'warn' : 'neutral';
    const relPe = x.relative_pe_to_spx_snapshot == null ? '-' : `${f(x.relative_pe_to_spx_snapshot, 2)}배`;

    box.innerHTML = `
      <div class="midcycle-head">
        <div>
          <small>Evercore ISI 역사 기준 · 기존 SOX 보조 해석</small>
          <h3>미드사이클 시계 ${x.score}/${x.total}</h3>
        </div>
        <span class="badge ${badgeClass}">${x.judgement}</span>
      </div>
      <div class="midcycle-metrics">
        <div><span>SOX 고점 대비</span><b>${f(x.drawdown_pct)}%</b><small>고점 ${x.peak_date || '-'}</small></div>
        <div><span>조정 기간</span><b>${f(x.calendar_weeks_since_peak, 1)}주</b><small>${f(x.trading_days_since_peak, 0)}거래일</small></div>
        <div><span>S&P500 대비</span><b>${f(x.sox_relative_return_vs_spx_pct)}%p</b><small>같은 고점 날짜 기준</small></div>
        <div><span>SOX/SPX 상대 PER</span><b>${relPe}</b><small>수동 스냅샷 ${x.relative_pe_reference_date || '-'}</small></div>
      </div>
      <div class="midcycle-conditions">${conditions}</div>
      <div class="midcycle-reading"><b>현재 해석</b><p>${x.interpretation}</p></div>
      <div class="midcycle-history">역사적 조정 후 평균 반등 ${f(x.historical_post_correction_bounce_pct)}% / 평균 ${f(x.historical_post_correction_bounce_weeks, 0)}주. 이는 목표수익률이 아니라 과거 6개 사례의 조건부 참고 통계입니다.</div>
      <div class="status-line">낙폭·기간·상대성과는 매일 자동 갱신 · 상대 PER는 기관 자료 입수 시 수동 갱신 · 0/4 추세 반등 점수에는 미포함</div>`;
  };
})();
