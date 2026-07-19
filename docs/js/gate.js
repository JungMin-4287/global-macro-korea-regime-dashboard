DASH.renderTrendGate=()=>{
  const gate=DASH.data?.trend_rebound_gate||{},el=document.getElementById('trendGate'),f=DASH.f;
  if(!el)return;
  const items=gate.components||[];
  if(!items.length){
    el.innerHTML='<article class="trend-gate-card"><div><b>추세 반등 게이트</b><span>데이터 갱신 후 표시됩니다.</span></div></article>';
    return;
  }
  const score=Number(gate.score||0),total=Number(gate.total||4);
  const cls=score>=4?'gate-good':score>=2?'gate-warn':'gate-bad';
  const chips=items.map(x=>`<div class="gate-chip ${x.confirmed?'confirmed':x.partial?'partial':'waiting'}"><span>${x.confirmed?'✓':x.partial?'△':'×'}</span><div><b>${x.name}</b><small>${x.short||x.summary||'-'}</small></div></div>`).join('');
  el.innerHTML=`<article class="trend-gate-card ${cls}"><div class="gate-head"><div><span class="gate-kicker">매수 등급 상향 조건</span><h2>추세 반등 게이트 <strong>${score}/${total}</strong></h2><p>${gate.judgement||'판정 미산출'}</p></div><div class="gate-score">${score}<small>/ ${total}</small></div></div><div class="gate-components">${chips}</div><div class="gate-foot"><b>현재 해석:</b> ${gate.interpretation||'-'}<span>${gate.note||''}</span></div></article>`;
};

DASH.augmentMacroVolatility=()=>{
  const macro=DASH.data?.macro_context||{},fx=macro.usdkrw||{},metrics=document.getElementById('vkospiMetrics'),text=document.getElementById('vkospiText'),f=DASH.f;
  if(!metrics||!fx||fx.close==null)return;
  const extra=`<div class="metric macro-metric"><span class="muted">원/달러</span><b>${f(fx.close,1)}원</b><small>5일 ${f(fx.change_5d_pct)}%</small></div><div class="metric macro-metric"><span class="muted">환율 20일 변동성</span><b>${f(fx.realized_vol_20d_pct)}%</b><small>5일 전 대비 ${f(fx.vol_change_5d_pp)}%p</small></div>`;
  if(!metrics.querySelector('.macro-metric'))metrics.insertAdjacentHTML('beforeend',extra);
  if(text&&!text.querySelector('.macro-combined')){
    const box=document.createElement('div');
    box.className='macro-combined';
    box.innerHTML=`<b>환율·변동성 결합:</b> ${macro.combined_interpretation||fx.interpretation||'-'}<div class="status-line">원/달러 ${fx.source||'-'} · 기준일 ${fx.date||'-'}</div>`;
    text.appendChild(box);
  }
};
