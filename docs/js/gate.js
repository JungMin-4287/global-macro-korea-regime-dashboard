DASH.renderTrendGate=()=>{
  const gate=DASH.data?.trend_rebound_gate||{},el=document.getElementById('trendGate');
  if(!el)return;
  const items=gate.components||[];
  if(!items.length){
    el.innerHTML='<article class="trend-gate-card"><div><b>추세 반등 게이트</b><span>데이터 갱신 후 표시됩니다.</span></div></article>';
    return;
  }

  const score=Number(gate.score||0),total=Number(gate.total||4);
  const partialCount=items.filter(x=>!x.confirmed&&x.partial).length;
  const progressScore=Math.min(total,score+partialCount*.5);
  const progressPct=total?Math.round(progressScore/total*100):0;
  const cls=score>=4?'gate-good':score>=2?'gate-warn':'gate-bad';
  const generatedDate=(DASH.data?.generated_at||'').slice(0,10);
  const storageKey='trendReboundGateSnapshot';
  let previousScore=gate.previous_score;
  let previousDate=gate.previous_date;
  try{
    const saved=JSON.parse(localStorage.getItem(storageKey)||'null');
    if(previousScore==null&&saved&&saved.date&&saved.date!==generatedDate)previousScore=Number(saved.score);
    if(!previousDate&&saved&&saved.date!==generatedDate)previousDate=saved.date;
    if(generatedDate)localStorage.setItem(storageKey,JSON.stringify({date:generatedDate,score}));
  }catch(e){}
  const change=gate.score_change!=null?Number(gate.score_change):(previousScore!=null?score-Number(previousScore):null);
  const changeText=change==null?'비교값 없음':change>0?`전일 대비 +${change}`:change<0?`전일 대비 ${change}`:'전일과 동일';
  const changeClass=change==null?'flat':change>0?'up':change<0?'down':'flat';

  const chips=items.map((x,i)=>{
    const state=x.confirmed?'confirmed':x.partial?'partial':'waiting';
    const icon=x.confirmed?'✓':x.partial?'△':'×';
    const status=x.confirmed?'충족':x.partial?'진행 중':'미충족';
    return `<div class="gate-chip ${state}"><span>${icon}</span><div><b>${i+1}. ${x.name}</b><em>${status}</em><small>${x.short||x.summary||'-'}</small></div></div>`;
  }).join('');
  const unmet=items.filter(x=>!x.confirmed).map(x=>`<li><b>${x.name}</b><span>${x.short||x.summary||'확인 대기'}</span></li>`).join('');
  const unmetBox=unmet?`<div class="gate-unmet"><b>미충족·확인 대기 조건</b><ul>${unmet}</ul></div>`:'<div class="gate-unmet all-clear"><b>4개 조건 모두 충족</b><span>치명적 위험이 없는지 최종 확인이 필요합니다.</span></div>';

  el.innerHTML=`<article class="trend-gate-card ${cls}">
    <div class="gate-head"><div><span class="gate-kicker">매수 등급 상향 조건</span><h2>추세 반등 게이트 <strong>${score}/${total}</strong></h2><p>${gate.judgement||'판정 미산출'}</p></div><div class="gate-score">${score}<small>/ ${total}</small></div></div>
    <div class="gate-progress-row"><div class="gate-progress-label"><b>확인 진행률 ${progressPct}%</b><span>확정 ${score}개 · 부분 개선 ${partialCount}개</span></div><div class="gate-change ${changeClass}">${changeText}${previousDate?` <small>(${previousDate})</small>`:''}</div></div>
    <div class="gate-progress"><i style="width:${progressPct}%"></i></div>
    <div class="gate-components">${chips}</div>${unmetBox}
    <div class="gate-foot"><b>현재 해석:</b> ${gate.interpretation||'-'}<span>${gate.note||''}</span></div>
  </article>`;
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