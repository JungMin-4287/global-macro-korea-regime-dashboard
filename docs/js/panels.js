DASH.renderStudy=()=>{
  const x=DASH.data.event_studies?.SOX||{},f=DASH.f;
  document.getElementById('eventStudy').innerHTML=`<div class="metrics"><div class="metric"><span class="muted">표본</span><b>${f(x.sample_count,0)}회</b></div><div class="metric"><span class="muted">5일 평균</span><b>${f(x.avg_5d)}%</b></div><div class="metric"><span class="muted">20일 평균</span><b>${f(x.avg_20d)}%</b></div><div class="metric"><span class="muted">60일 평균</span><b>${f(x.avg_60d)}%</b></div><div class="metric"><span class="muted">5일 상승확률</span><b>${f(x.positive_5d_pct)}%</b></div><div class="metric"><span class="muted">20일 상승확률</span><b>${f(x.positive_20d_pct)}%</b></div><div class="metric"><span class="muted">60일 상승확률</span><b>${f(x.positive_60d_pct)}%</b></div><div class="metric"><span class="muted">-30% 전이</span><b>${f(x.transition_to_minus30_pct)}%</b></div></div><div class="status-line">표본 기간 ${x.period_start||'-'} ~ ${x.period_end||'-'}</div>`;
};

DASH.renderVal=()=>{
  const v=DASH.data.valuation||{},f=DASH.f,rows=v.rows||[];
  document.getElementById('valuationTable').innerHTML=rows.map(x=>`<tr><td>${x.name}</td><td>${f(x.price,0)}</td><td>${f(x.eps_2026,0)}</td><td>${f(x.per_2026)}배</td><td>${f(x.eps_2027,0)}</td><td>${f(x.per_2027)}배</td><td>${f(x.eps_2028,0)}</td><td>${f(x.per_2028)}배</td><td style="text-align:left">${x.interpretation}</td></tr>`).join('');
  const mobile=document.getElementById('valuationMobile');
  if(mobile)mobile.innerHTML=rows.map(x=>`<article class="valuation-card"><h3>${x.name}</h3><div class="valuation-grid"><div class="cell"><span>현재가</span><b>${f(x.price,0)}원</b></div><div class="cell"><span>12MF 근사 PER</span><b>${f(x.per_2026)}배</b></div><div class="cell"><span>2027F PER</span><b>${f(x.per_2027)}배</b></div><div class="cell"><span>2028F PER</span><b>${f(x.per_2028)}배</b></div><div class="cell"><span>2027E EPS</span><b>${f(x.eps_2027,0)}원</b></div><div class="cell"><span>2028E EPS</span><b>${f(x.eps_2028,0)}원</b></div></div><div class="status-line" style="margin-top:9px">${x.interpretation||''}</div></article>`).join('');
  document.getElementById('valuationNote').textContent=`기준 EPS: ${v.source||'-'} (${v.reference_date||'-'}). ${v.note||''} 저PER이라도 EPS 하향 가속·호재 불반응이면 매수 신호로 쓰지 않습니다.`;
};

DASH.findXForY=(rows,xKey,yKey,target)=>{
  if(!Array.isArray(rows)||rows.length<2||target==null)return null;
  const a=[...rows].sort((x,y)=>x[xKey]-y[xKey]);
  for(let i=1;i<a.length;i++){
    const p=a[i-1],q=a[i],y1=Number(p[yKey]),y2=Number(q[yKey]);
    if((target-y1)*(target-y2)<=0&&y1!==y2){const t=(target-y1)/(y2-y1);return Number(p[xKey])+t*(Number(q[xKey])-Number(p[xKey]))}
  }
  return null;
};

DASH.renderStress=()=>{
  const D=DASH.data,x=D.manual?.earnings_stress_reference;
  if(!x)return;
  const f=DASH.f,C=DASH.C,rows=x.scenarios||[],ref=Number(x.reference_index_level),current=Number(D.assets?.KOSPI?.close),scale=Number.isFinite(current)&&ref>0?current/ref:null,normal=Number(x.normalized_per||10);
  const currentRows=rows.map(r=>({...r,current_per:scale==null?null:Number(r.kospi200_per)*scale}));
  const implied=DASH.findXForY(currentRows,'earnings_decline_pct','current_per',normal);
  const samsung=implied==null?null:DASH.interpolate(rows,'earnings_decline_pct','samsung_net_income_trn_krw',implied);
  const hynix=implied==null?null:DASH.interpolate(rows,'earnings_decline_pct','skhynix_net_income_trn_krw',implied);
  const refChange=scale==null?null:(scale-1)*100;
  const currentBasePer=scale==null?null:Number(x.reference_12m_forward_per)*scale;
  const hist=Math.abs(Number(x.historical_downcycle_average_earnings_decline_pct||0));
  const gap=implied==null?null:implied-hist;

  document.getElementById('stressSummary').innerHTML=`<div class="metric"><span class="muted">장표 기준 지수</span><b>${f(ref,1)}</b><small>${x.reference_date||'-'}</small></div><div class="metric"><span class="muted">현재 KOSPI</span><b>${f(current,1)}</b><small>기준 대비 ${f(refChange)}%</small></div><div class="metric"><span class="muted">현재 환산 PER</span><b>${f(currentBasePer)}배</b><small>감익 0% 가정</small></div><div class="metric"><span class="muted">10배 도달 감익률</span><b>${f(implied,1)}%</b><small>시장에 내재된 비관</small></div>`;

  const currentBox=document.getElementById('stressCurrent');
  if(currentBox)currentBox.innerHTML=scale==null?'<b>현재 위치 미산출</b><br>KOSPI 최신값을 받지 못해 현재 지수 환산 위치를 표시하지 못했습니다.':`<b>현재 숫자를 쉽게 읽으면:</b><br>현재 지수에서 반도체 이익이 줄지 않는다고 가정하면 환산 PER는 약 <b>${f(currentBasePer)}배</b>입니다. 이익이 줄어 PER가 장기 평균인 <b>${f(normal)}배</b>가 되려면, 장표 기준으로 반도체 이익이 약 <b>${f(implied,1)}%</b> 감소해야 합니다. 해당 감익률을 장표에 대입하면 삼성전자 순이익은 약 <b>${f(samsung,0)}조원</b>, SK하이닉스는 약 <b>${f(hynix,0)}조원</b>입니다.<div class="status-line">이 수치는 이익 전망이 아니라 현재 가격이 어느 정도의 악화를 견딜 수 있는지 보는 역산값입니다.</div>`;

  const decision=document.getElementById('stressDecision');
  if(decision){
    let cls='warn-conclusion',title='현재 판단: 전형적인 하락 사이클 수준을 점검하는 구간',body='현재 가격이 반영한 감익과 과거 평균 감익이 비슷합니다. 저평가만으로는 충분하지 않고 EPS 하향 둔화와 주가 반응 회복이 필요합니다.';
    if(implied==null){cls='bad-conclusion';title='현재 판단: 감익 반영도를 계산하지 못했습니다';body='현재 지수나 기준값이 없어 판단을 보류합니다.'}
    else if(gap>=15){cls='';title='현재 판단: 과거 평균보다 훨씬 큰 감익을 가격에 반영';body=`과거 하락 사이클 평균 감익 약 ${f(hist,1)}%보다 ${f(gap,1)}%p 더 큰 악화를 반영한 계산입니다. 실제 감익이 이보다 작고 EPS 하향 속도가 둔화되면 밸류에이션 안전마진이 될 수 있습니다. 다만 호재에도 주가가 계속 하락하면 아직 바닥 신호가 아닙니다.`}
    else if(gap<-5){cls='bad-conclusion';title='현재 판단: 과거 평균 감익보다 덜 반영';body=`현재 가격이 반영한 감익은 과거 평균 약 ${f(hist,1)}%보다 작습니다. 업황 우려가 계속 커지면 추가 가격 조정 여지가 남아 있다는 뜻입니다.`}
    decision.className=`plain-conclusion ${cls}`;
    decision.innerHTML=`<b>${title}</b><div style="margin-top:6px">${body}</div>`;
  }

  const perCanvas=document.getElementById('stressPer');
  if(perCanvas)new Chart(perCanvas,{type:'line',data:{datasets:[
    {label:'기준일 PER 곡선',data:rows.map(r=>({x:r.earnings_decline_pct,y:r.kospi200_per})),borderColor:C.w,backgroundColor:'rgba(255,189,74,.08)',pointRadius:3,borderWidth:2},
    {label:'현재 지수 환산 PER',data:currentRows.map(r=>({x:r.earnings_decline_pct,y:r.current_per})),borderColor:C.a,pointRadius:3,borderWidth:2,borderDash:[5,4]},
    {label:'현재 10배 위치',type:'scatter',data:implied==null?[]:[{x:implied,y:normal}],backgroundColor:C.r,borderColor:'#fff',borderWidth:1.5,pointRadius:7}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}},tooltip:{callbacks:{title:i=>`감익률 ${f(i[0]?.parsed?.x,1)}%`,label:i=>`${i.dataset.label}: ${f(i.parsed.y)}배`}}},scales:{x:{type:'linear',min:0,max:90,title:{display:true,text:'반도체 감익률(%)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}},y:{title:{display:true,text:'PER(배)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}}});

  const profitCanvas=document.getElementById('stressProfit');
  if(profitCanvas)new Chart(profitCanvas,{type:'line',data:{datasets:[
    {label:'삼성전자 순이익',data:rows.map(r=>({x:r.earnings_decline_pct,y:r.samsung_net_income_trn_krw})),borderColor:C.a,pointRadius:3,borderWidth:2},
    {label:'SK하이닉스 순이익',data:rows.map(r=>({x:r.earnings_decline_pct,y:r.skhynix_net_income_trn_krw})),borderColor:C.c,pointRadius:3,borderWidth:2},
    {label:'현재 감익 위치',type:'scatter',data:implied==null?[]:[{x:implied,y:samsung},{x:implied,y:hynix}],backgroundColor:C.r,borderColor:'#fff',borderWidth:1.5,pointRadius:6}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}},tooltip:{callbacks:{title:i=>`감익률 ${f(i[0]?.parsed?.x,1)}%`,label:i=>`${i.dataset.label}: ${f(i.parsed.y,0)}조원`}}},scales:{x:{type:'linear',min:0,max:90,title:{display:true,text:'반도체 감익률(%)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}},y:{title:{display:true,text:'순이익(조원)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}}});

  document.getElementById('stressTable').innerHTML=rows.map(r=>`<tr><td>${r.earnings_decline_pct}%</td><td>${r.kospi200_per}배</td><td>${r.samsung_net_income_trn_krw}조원</td><td>${r.skhynix_net_income_trn_krw}조원</td></tr>`).join('');
  document.getElementById('stressText').innerHTML=`<b>실제 투자 판단은 이렇게 합니다.</b><br>① 실제 이익 감소가 내재 감익률보다 작고 EPS 하향이 멈추면 저평가 근거가 강해집니다.<br>② 실제 감익이 내재 감익률보다 커지거나 EPS 하향이 계속 가속되면 낮은 PER는 ‘싸 보이는 함정’일 수 있습니다.<br>③ 따라서 이 장표는 단독 매수 신호가 아니라 호재·악재에 대한 주가 반응, 외국인 수급, VKOSPI 고점 통과와 함께 사용합니다.<div class="status-line">기준일 ${x.reference_date}. 노란선은 기준 장표, 파란 점선은 현재 지수 수준의 단순 환산입니다. 실시간 증권사 컨센서스 자체가 아닙니다.</div>`;
};

DASH.renderOther=()=>{
  const D=DASH.data,f=DASH.f;
  document.getElementById('breadth').innerHTML=['KOSPI','KOSDAQ'].map(k=>{const b=D.breadth?.[k]||{};return `<tr><td>${k}</td><td>${f(b.advancers,0)}</td><td>${f(b.decliners,0)}</td><td>${f(b.ad_ratio)}</td></tr>`}).join('');
  const ratio=D.breadth?.KOSPI?.ad_ratio;
  document.getElementById('breadthText').innerHTML=ratio==null?'시장 폭 미산출':ratio<0.5?'하락 종목이 상승 종목의 2배 이상입니다. 지수 반등이 나와도 폭이 좁으면 신뢰도를 낮춥니다.':ratio<1?'하락 종목 우위로 시장 내부는 아직 약합니다.':'상승 종목 우위로 반등 확산성이 개선됐습니다.';
  const p=D.manual?.positioning||{};
  document.getElementById('positioning').innerHTML=`<div class="metrics"><div class="metric"><span class="muted">미국 반도체 L/S</span><b>${f(p.us_semiconductor_ls_percentile)}%</b></div><div class="metric"><span class="muted">미국 20일 flow z</span><b>${f(p.us_semiconductor_flow_20d_z)}</b></div><div class="metric"><span class="muted">아시아 L/S</span><b>${f(p.asia_supply_chain_ls_percentile)}%</b></div><div class="metric"><span class="muted">아시아 flow z</span><b>${f(p.asia_supply_chain_flow_20d_z)}</b></div></div><div class="note" style="margin-top:12px">${p.us_semiconductor_ls_percentile>=90?'미국 반도체 포지셔닝은 여전히 매우 혼잡합니다. -20% 낙폭만으로 투매 완료를 선언하기 어렵습니다.':'포지셔닝 혼잡도가 완화되고 있습니다.'}<div class="status-line">${p.note||''}</div></div>`;
};

DASH.renderErrors=()=>{
  const entries=Object.entries(DASH.data.errors||{});
  document.getElementById('errors').innerHTML=entries.length?entries.map(([k,v])=>`<div><b>${k}</b>: ${v}</div>`).join(''):'모든 핵심 데이터가 정상 수집됐습니다.';
};
