DASH.renderAsset=(k,a)=>{
  const C=DASH.C,h=(a.history||[]).slice(-260),l=h.map(x=>x.date),s=DASH.s,line=DASH.line;
  if(!h.length)return;
  if(['KOSPI','KOSDAQ'].includes(k)){
    line(k+'-price',l,[
      {label:a.name,data:s(h,'close'),borderColor:C.p,pointRadius:0,borderWidth:2},
      {label:'50일선',data:s(h,'sma50'),borderColor:C.b,pointRadius:0},
      {label:'120일선',data:s(h,'sma120'),borderColor:C.c,pointRadius:0}
    ]);
    const refs=k==='KOSPI'?[102,93,91]:[95,93,80,77];
    line(k+'-ratio',l,[
      {label:'50일 이격도',data:s(h,'ratio50'),borderColor:C.w,pointRadius:0,borderWidth:2},
      {label:'120일 이격도',data:s(h,'ratio120'),borderColor:C.g,pointRadius:0,borderWidth:2},
      {label:'100',data:l.map(()=>100),borderColor:C.p,borderDash:[5,5],pointRadius:0},
      ...refs.map((v,i)=>({label:'역사 참고 '+v,data:l.map(()=>v),borderColor:[C.a,C.w,C.r,C.c][i%4],borderDash:[3,5],borderWidth:1,pointRadius:0}))
    ]);
    DASH.setInterpretation(k+'-interpretation',a);
  }else if(['SAMSUNG','SKHYNIX'].includes(k)){
    line(k+'-price',l,[
      {label:a.name,data:s(h,'close'),borderColor:C.p,pointRadius:0,borderWidth:2},
      {label:'30일선',data:s(h,'sma30'),borderColor:C.a,pointRadius:0},
      {label:'50일선',data:s(h,'sma50'),borderColor:C.b,pointRadius:0},
      {label:'120일선',data:s(h,'sma120'),borderColor:C.c,pointRadius:0}
    ]);
    line(k+'-ratio',l,[
      {label:'30일 이격도',data:s(h,'ratio30'),borderColor:C.w,pointRadius:0,borderWidth:2},
      {label:'50일 이격도',data:s(h,'ratio50'),borderColor:C.b,pointRadius:0},
      {label:'100',data:l.map(()=>100),borderColor:C.p,borderDash:[5,5],pointRadius:0},
      {label:'110',data:l.map(()=>110),borderColor:C.r,borderDash:[5,5],pointRadius:0},
      {label:'115',data:l.map(()=>115),borderColor:C.c,borderDash:[3,5],pointRadius:0}
    ]);
    DASH.setInterpretation(k+'-interpretation',a);
  }else if(k==='SOX'){
    line('SOX-price',l,[
      {label:'SOX',data:s(h,'close'),borderColor:C.p,pointRadius:0,borderWidth:2},
      {label:'50일선',data:s(h,'sma50'),borderColor:C.b,pointRadius:0},
      {label:'100일선',data:s(h,'sma100'),borderColor:C.g,pointRadius:0},
      {label:'200일선',data:s(h,'sma200'),borderColor:C.w,pointRadius:0}
    ]);
    line('SOX-ratio',l,[
      {label:'50일 이격도',data:s(h,'ratio50'),borderColor:C.b,pointRadius:0},
      {label:'100일 이격도',data:s(h,'ratio100'),borderColor:C.g,pointRadius:0},
      {label:'200일 이격도',data:s(h,'ratio200'),borderColor:C.w,pointRadius:0},
      {label:'100',data:l.map(()=>100),borderColor:C.p,borderDash:[5,5],pointRadius:0}
    ]);
    DASH.setInterpretation('SOX-interpretation',a);
  }
};

DASH.linearFit=points=>{
  if(!points.length)return[];
  const xs=points.map(p=>Number(p.x)),ys=points.map(p=>Number(p.y));
  const mx=xs.reduce((a,b)=>a+b,0)/xs.length,my=ys.reduce((a,b)=>a+b,0)/ys.length;
  const den=xs.reduce((s,x)=>s+(x-mx)*(x-mx),0);
  const slope=den===0?0:xs.reduce((sum,x,i)=>sum+(x-mx)*(ys[i]-my),0)/den;
  const intercept=my-slope*mx,min=Math.min(...xs),max=Math.max(...xs);
  return [{x:min,y:slope*min+intercept},{x:max,y:slope*max+intercept}];
};

DASH.renderCorrectionFlow=m=>{
  const e=document.getElementById('correctionFlow'),metrics=document.getElementById('correctionFlowMetrics'),text=document.getElementById('correctionFlowText'),f=DASH.f,C=DASH.C;
  if(!e||!metrics||!text)return;
  const points=(m.points||[]).map(d=>({x:Number(d.x),y:Number(d.y),date:d.date,peak_date:d.peak_date,close:d.close})).filter(d=>Number.isFinite(d.x)&&Number.isFinite(d.y));
  if(!points.length){
    e.parentElement.innerHTML='<div class="plain-conclusion bad-conclusion"><b>누적 수급 지도 미산출</b><br>개인 순매수와 KOSPI 가격의 공통 날짜가 부족합니다. 다음 자동 실행에서 KRX·네이버 금융을 다시 조회합니다.</div>';
    metrics.innerHTML='<div class="metric"><span class="muted">현재 낙폭</span><b>-</b></div><div class="metric"><span class="muted">개인 누적순매수</span><b>-</b></div><div class="metric"><span class="muted">조정 시작일</span><b>-</b></div><div class="metric"><span class="muted">현재 구간</span><b>미산출</b></div>';
    text.innerHTML=`<div class="headline">현재 판단을 만들 수 없습니다.</div><div>${m.interpretation||m.error||'수급 데이터 미산출'}</div>`;
    return;
  }
  const regression=(m.regression||DASH.linearFit(points)).map(d=>({x:Number(d.x),y:Number(d.y)}));
  const marked=(m.highlights||[]).map(d=>({x:Number(d.x),y:Number(d.y),date:d.date,label:d.label})).filter(d=>Number.isFinite(d.x)&&Number.isFinite(d.y));
  const latest=m.latest||points[points.length-1];
  new Chart(e,{type:'scatter',data:{datasets:[
    {label:'조정구간 일별 관측치',data:points,backgroundColor:'rgba(160,180,205,.62)',borderColor:'rgba(110,130,155,.8)',pointRadius:3.3},
    {label:'평균 관계',type:'line',data:regression,borderColor:C.a,borderDash:[6,5],borderWidth:2,pointRadius:0},
    {label:'현재',data:[{x:Number(latest.x),y:Number(latest.y),date:latest.date}],backgroundColor:C.r,borderColor:'#fff',borderWidth:2,pointRadius:9},
    {label:'주요 변곡',data:marked,backgroundColor:C.w,borderColor:'#9b6b00',borderWidth:2,pointRadius:7}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}},pointLabels:{enabled:true,datasetIndex:3},tooltip:{callbacks:{label:ctx=>{const d=ctx.raw||{};return `${d.date||ctx.dataset.label}: 개인 누적 ${f(d.x)}조원 · 낙폭 ${f(d.y)}%`}}}},scales:{x:{title:{display:true,text:'고점 이후 개인 누적순매수(조원)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}},y:{title:{display:true,text:'KOSPI 고점 대비 낙폭(%)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}}});

  const x=Number(latest.x),y=Number(latest.y),zone=m.zone||'관찰';
  let action='외국인 현물·선물 수급과 시장 폭을 함께 확인합니다.';
  if(y<=-20&&x>5)action='개인이 대규모로 물량을 받았는데도 지수가 깊게 하락했습니다. 외국인 순매수 전환과 종가 회복 전에는 청산 완료로 판단하지 않습니다.';
  else if(y<=-20&&x<=0)action='개인 투매가 동반된 극단 구간입니다. 매도 고갈 후보지만 VKOSPI가 고점을 통과하고 지수가 전저점을 지키는지 확인합니다.';
  else if(y<=-10&&x>0)action='개인 저가매수가 누적되고 있습니다. 가격 반전 없이 누적매수만 커지면 물타기 위험으로 봅니다.';
  metrics.innerHTML=`<div class="metric"><span class="muted">현재 낙폭</span><b>${f(y)}%</b></div><div class="metric"><span class="muted">개인 누적순매수</span><b>${f(x)}조원</b></div><div class="metric"><span class="muted">조정 시작일</span><b>${latest.peak_date||'-'}</b></div><div class="metric"><span class="muted">현재 구간</span><b>${zone}</b></div>`;
  text.innerHTML=`<div class="headline">현재 위치: ${zone}</div><div><b>무슨 뜻?</b> ${m.interpretation||''}</div><div class="action"><b>투자 판단:</b> ${action}</div><div class="status-line">${m.window||''} · ${m.source||'-'} · 기준일 ${latest.date||'-'}</div>`;
};

DASH.renderPsychology=p=>{
  DASH.renderCorrectionFlow(p.correction_map||{});
  const e=document.getElementById('psychology'),points=p.points||[],highlights=p.highlights||[],f=DASH.f,C=DASH.C,metrics=document.getElementById('psychologyMetrics'),text=document.getElementById('psychologyText');
  if(!points.length){
    if(e&&e.parentElement)e.parentElement.innerHTML='<div class="note bad-note"><b>수급 데이터 미산출</b><br>KRX와 네이버 금융을 순차 조회했지만 가격 데이터와 결합할 수 있는 개인 순매수 시계열을 받지 못했습니다.</div>';
    metrics.innerHTML='<div class="metric"><span class="muted">현재 구간</span><b>미산출</b></div><div class="metric"><span class="muted">개인 순매수</span><b>-</b></div><div class="metric"><span class="muted">KOSPI 수익률</span><b>-</b></div><div class="metric"><span class="muted">과거 패턴 대비</span><b>-</b></div>';
    text.innerHTML=`<div class="headline">현재 판단을 만들 수 없습니다.</div><div>${p.interpretation||'개인 순매수 데이터 미산출'}</div><div class="status-line">${p.source||p.error||'다음 자동 실행에서 재시도합니다.'}</div>`;
    return;
  }
  const scatter=points.map(d=>({x:Number(d.y),y:Number(d.x),date:d.date}));
  const fit=DASH.linearFit(scatter);
  const marked=highlights.map(d=>({x:Number(d.y),y:Number(d.x),label:d.label,date:d.date}));
  new Chart(e,{type:'scatter',data:{datasets:[
    {label:'일별 관측치',data:scatter,backgroundColor:'rgba(160,180,205,.68)',borderColor:'rgba(110,130,155,.85)',pointRadius:3.5},
    {label:'평소 수급 패턴',type:'line',data:fit,borderColor:C.a,borderDash:[6,5],borderWidth:2,pointRadius:0},
    {label:'최근',data:scatter.slice(-1),backgroundColor:C.w,borderColor:'#9b6b00',borderWidth:2,pointRadius:8},
    {label:'주요 변곡',data:marked,backgroundColor:'#ff9d3f',borderColor:'#4b2a00',borderWidth:2,pointRadius:7}
  ]},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'nearest',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}},quadrantBackground:{enabled:true},pointLabels:{enabled:true,datasetIndex:3},tooltip:{callbacks:{label:ctx=>{const d=ctx.raw||{};return `${d.date||ctx.dataset.label}: KOSPI ${f(d.x)}% · 개인 ${f(d.y)}조원`}}}},scales:{x:{title:{display:true,text:'KOSPI 수익률(%)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}},y:{title:{display:true,text:'개인 순매수(조원)',color:'#95a3bd'},ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}}});

  const z=p.latest||{},ret=Number(z.y),buy=Number(z.x),res=Number(z.residual);
  let zone='중립 수급',meaning='개인 수급과 지수 움직임이 평소 범위에 있습니다.',action='추가 방향 확인이 필요합니다.';
  if(ret<0&&buy<0){zone='공포·투매 후보';meaning='지수가 하락하는데 개인도 함께 팔았습니다. 평소의 저가매수 행동마저 약해진 강한 공포 구간입니다.';action='매도 고갈 후보이지만 다음 거래일 저점 방어와 VKOSPI 하락 전환 전에는 매수 신호로 보지 않습니다.'}
  else if(ret>0&&buy>0){zone='탐욕·추격 후보';meaning='지수가 오르는 날 개인도 순매수했습니다. 상승을 뒤늦게 따라붙는 추격매수일 수 있습니다.';action='추세가 이어질 수 있으나 이격도 확대와 거래대금 급증이 겹치면 신규 추격매수를 줄입니다.'}
  else if(ret<0&&buy>0){zone='개인 저가매수·지수 하락';meaning='개인이 외국인·기관 매물을 받아냈지만 지수는 하락했습니다. 매도 압력이 개인 매수보다 강한 상태입니다.';action='청산이 끝났다고 보기 어렵습니다. 외국인 수급 반전과 종가 회복을 확인합니다.'}
  else if(ret>0&&buy<0){zone='외국인·기관 주도 상승';meaning='개인이 파는데도 지수가 올랐습니다. 외국인·기관이 가격을 끌어올리는 비교적 건전한 수급입니다.';action='시장 폭까지 개선되면 반등 신뢰도를 높입니다.'}
  const residualText=Number.isFinite(res)?(res<-1?'과거 관계보다 지수 반응이 더 약합니다.':res>1?'과거 관계보다 지수 반응이 더 강합니다.':'과거 수급 관계에서 크게 벗어나지 않았습니다.'):'회귀 잔차는 미산출입니다.';
  metrics.innerHTML=`<div class="metric"><span class="muted">현재 구간</span><b>${zone}</b></div><div class="metric"><span class="muted">개인 순매수</span><b>${f(buy)}조원</b></div><div class="metric"><span class="muted">KOSPI 수익률</span><b>${f(ret)}%</b></div><div class="metric"><span class="muted">과거 패턴 대비</span><b>${f(res)}%p</b></div>`;
  text.innerHTML=`<div class="headline">오늘 위치: ${zone}</div><div><b>무슨 뜻?</b> ${meaning} ${residualText}</div><div class="action"><b>투자 판단:</b> ${action}</div><div class="status-line">상관계수 ${f(p.correlation)} · 기준일 ${z.date||'-'} · ${p.source||'-'}<br>${p.highlight_note||''}</div>`;
};

DASH.renderEnv=()=>{
  const D=DASH.data,C=DASH.C,s=DASH.s,line=DASH.line,f=DASH.f,nd=D.assets?.NDX,v=D.assets?.VKOSPI,k=D.assets?.KOSPI;
  if(nd){
    const h=(nd.history||[]).slice(-260),l=h.map(x=>x.date);
    line('NDX-price',l,[{label:'나스닥100',data:s(h,'close'),borderColor:C.p,pointRadius:0,borderWidth:2},{label:'100일선',data:s(h,'sma100'),borderColor:C.a,pointRadius:0}]);
    DASH.setInterpretation('ndxText',nd);
  }else document.getElementById('ndxText').innerHTML='나스닥100 데이터 미산출';

  const vm=document.getElementById('vkospiMetrics'),vt=document.getElementById('vkospiText'),canvas=document.getElementById('VKOSPI-price');
  if(v&&canvas){
    const h=(v.history||[]).filter(row=>Number.isFinite(Number(row.close))).slice(-260);
    const labels=h.map(x=>x.date),closes=h.map(x=>Number(x.close)),sma20=h.map(x=>Number.isFinite(Number(x.sma20))?Number(x.sma20):null),sma50=h.map(x=>Number.isFinite(Number(x.sma50))?Number(x.sma50):null);
    const level=Number(v.close),dailyMove=Number.isFinite(level)?level/Math.sqrt(252):null;
    const last3=closes.slice(-3),falling=last3.length>=2&&last3[last3.length-1]<last3[last3.length-2],twoDayFall=last3.length>=3&&last3[2]<last3[1]&&last3[1]<last3[0];
    const recentHigh=closes.length?Math.max(...closes.slice(-20)):null,offHigh=recentHigh&&Number.isFinite(level)?(level/recentHigh-1)*100:null;
    vm.innerHTML=`<div class="metric"><span class="muted">현재 VKOSPI</span><b>${f(level)}</b></div><div class="metric"><span class="muted">하루 예상 변동폭</span><b>±${f(dailyMove)}%</b><small>연환산값 단순 환산</small></div><div class="metric"><span class="muted">20일 평균</span><b>${f(v.sma20)}</b></div><div class="metric"><span class="muted">20일 고점 대비</span><b>${f(offHigh)}%</b></div>`;
    if(h.length){
      const pointRadius=h.length<3?7:h.length<15?3:0;
      const datasets=[{label:v.is_proxy?'KOSPI 20일 실현변동성(대체)':'VKOSPI',data:closes,borderColor:C.r,backgroundColor:'rgba(255,101,119,.12)',fill:true,pointRadius,borderWidth:3,spanGaps:true,tension:.18}];
      if(sma20.some(Number.isFinite))datasets.push({label:'20일 평균',data:sma20,borderColor:C.w,pointRadius:0,borderWidth:1.7,spanGaps:true});
      if(sma50.some(Number.isFinite))datasets.push({label:'50일 평균',data:sma50,borderColor:C.a,pointRadius:0,borderWidth:1.7,spanGaps:true});
      const min=Math.min(...closes),max=Math.max(...closes),pad=Math.max(2,(max-min)*.12);
      new Chart(canvas,{type:'line',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}},tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${f(ctx.parsed.y)}`}}},scales:{x:{ticks:{color:'#95a3bd',maxTicksLimit:7},grid:{color:'rgba(43,59,94,.25)'}},y:{suggestedMin:min-pad,suggestedMax:max+pad,ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}}});
    }else{
      canvas.parentElement.innerHTML='<div class="plain-conclusion bad-conclusion"><b>VKOSPI 이력 미수집</b><br>현재값은 확인했지만 차트를 그릴 날짜별 시계열이 없습니다. 다음 자동 실행에서 Investing.com·KRX 이력을 다시 수집합니다.</div>';
    }
    const zone=v.disparity_interpretation?.zone||'관찰';
    let meaning=Number.isFinite(level)?`현재 ${f(level)}는 ${zone}입니다. 옵션시장은 하루 약 ±${f(dailyMove)}% 수준의 큰 움직임을 반영하고 있습니다.`:'현재 VKOSPI 수준을 계산하지 못했습니다.';
    let action='지수 반등과 VKOSPI 하락이 동시에 나오는지 확인합니다.';
    if(level>=50&&!falling)action='변동성이 아직 상승 또는 정체 중입니다. 공포가 크다는 이유만으로 바닥을 선언하지 않습니다.';
    if(level>=50&&twoDayFall)action='극단적 수준이지만 2거래일 연속 하락해 공포 정점 후보입니다. 시장 폭과 전저점 방어가 동반되면 분할매수 신뢰도가 높아집니다.';
    else if(level>=50&&falling)action='고점에서 한 차례 하락했습니다. 최소 한 번 더 하락하고 지수가 저점을 지키는지 확인합니다.';
    vt.className=`interpret note ${DASH.noteClass(zone)}`;
    vt.innerHTML=`<div class="headline">현재 판단: ${zone}</div><div><b>무슨 뜻?</b> ${meaning} VKOSPI ${f(level)}는 하락 확률 ${f(level)}%라는 뜻이 아닙니다.</div><div class="action"><b>투자 판단:</b> ${action}</div><div class="status-line">20일 평균 ${f(v.sma20)} · 50일 평균 ${f(v.sma50)} · 3년 백분위 ${f(v.level_percentile_3y,1)}% · ${v.source||'-'} · 기준일 ${v.date||'-'}</div>`;
  }else if(vt){
    if(vm)vm.innerHTML='';
    vt.innerHTML='<div class="headline">변동성 미산출</div><div>실제 VKOSPI 조회와 실현변동성 대체 계산이 모두 실패했습니다.</div><div class="action"><b>투자 판단:</b> 변동성 확인 전에는 과매도 매수 비중을 제한합니다.</div>';
  }

  if(k){
    const h=(k.history||[]).slice(-520),l=h.map(x=>x.date);
    line('KOSPI-ratio60',l,[{label:'60일 이격도',data:s(h,'ratio60'),borderColor:C.a,pointRadius:0,borderWidth:2},{label:'100',data:l.map(()=>100),borderColor:C.p,borderDash:[5,5],pointRadius:0},{label:'과거 비교 90',data:l.map(()=>90),borderColor:C.w,borderDash:[5,5],pointRadius:0}]);
    const r=k.ratio60,zone=r==null?'미산출':r<85?'2018년 이후 극단적 과매도':r<90?'역사적 과매도':r<100?'60일선 하회 조정':'60일선 위 중기 추세',msg=r<90?'과거 저점권이지만 낙하 중이면 추가 하락할 수 있습니다. VKOSPI 고점 통과와 전저점 방어를 함께 확인합니다.':r<100?'중기 조정 국면입니다. 100선 회복 전까지 반등 지속성을 낮게 봅니다.':'중기 추세는 유지되지만 110 이상이면 과열을 별도 점검합니다.';
    document.getElementById('kospi60Text').innerHTML=`<div class="headline">현재 구간: ${zone}</div><div>60일 이격도 ${f(r)} (${r==null?'-':f(r-100)}%).</div><div class="action"><b>해석:</b> ${msg}</div>`;
  }
};
