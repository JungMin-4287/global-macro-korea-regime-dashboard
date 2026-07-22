window.DASH={data:JSON.parse(document.getElementById('embedded').textContent)};
DASH.C={p:'#eef4ff',a:'#6fa8ff',b:'#59d9ef',c:'#b48cff',w:'#ffbd4a',g:'#42d49a',r:'#ff6577'};
DASH.f=(v,d=2)=>(v===null||v===undefined||Number.isNaN(v))?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d});
DASH.cls=s=>['반등 확인','과매도 접근','상승 추세','중기 상승 추세','안정'].some(x=>(s||'').includes(x))?'good':['낙하','훼손','공포','고변동성','위험','과열','위기'].some(x=>(s||'').includes(x))?'bad':['조정','눌림','불안','중립','경계'].some(x=>(s||'').includes(x))?'warn':'neutral';
DASH.noteClass=zone=>(zone||'').includes('반전')||(zone||'').includes('안정')?'good-note':(['낙하','위험','공포','과열','훼손','위기'].some(x=>(zone||'').includes(x))?'bad-note':'');
DASH.interpretationHTML=a=>{const x=a?.disparity_interpretation||{};return `<div class="headline">${x.headline||'현재 구간 미산출'}</div><div>${x.summary||''}</div><div class="action"><b>해석:</b> ${x.action||'데이터 갱신 후 표시됩니다.'}</div><div class="status-line">데이터: ${a?.source||'-'} · 기준일 ${a?.date||'-'}</div>`};
DASH.card=a=>{
  const x=a.disparity_interpretation||{},f=DASH.f;
  const zone=x.zone||a.signal||'관찰';
  const reading=x.action||x.summary||'데이터 갱신 후 해석이 표시됩니다.';
  if(a.name==='VKOSPI'){
    return `<article class="card summary-card volatility-card">
      <div class="kpi"><div><div class="name">VKOSPI</div><div class="value">${f(a.close)}</div><div class="muted summary-date">${a.date||'-'} · ${f(a.change_pct)}%</div></div><span class="badge ${DASH.cls(zone)}">${zone}</span></div>
      <div class="summary-metrics">
        <div class="metric"><span class="muted">20일 평균</span><b>${f(a.sma20)}</b></div>
        <div class="metric"><span class="muted">50일 평균</span><b>${f(a.sma50)}</b></div>
        <div class="metric"><span class="muted">3년 수준 백분위</span><b>${f(a.level_percentile_3y,1)}%</b></div>
      </div>
      <div class="summary-reading ${DASH.noteClass(zone)}"><strong>${x.headline||`현재 구간: ${zone}`}</strong><p>${reading}</p><div class="status-line">52주 범위 ${f(a.low_52w)}~${f(a.high_52w)} · ${a.source||'-'}</div></div>
    </article>`;
  }
  const isStock=['stock','global_stock'].includes(a.type),isNDX=a.name==='나스닥100';
  const ratio=isStock?a.ratio30:(isNDX?a.ratio100:a.ratio50);
  const ratioLabel=isStock?'30일 이격도':isNDX?'100일 이격도':'50일 이격도';
  const t=a.technical_rebound||{},fresh=a.freshness||{};
  const stale=fresh.stale?`<span class="badge bad">${fresh.business_days_late??'?'}일 지연</span>`:'';
  return `<article class="card summary-card">
    <div class="kpi"><div><div class="name">${a.name}</div><div class="value">${f(a.close,0)}</div><div class="muted summary-date">${a.date||'-'} · ${f(a.change_pct)}%</div></div><div>${stale}<span class="badge ${DASH.cls(zone)}">${zone}</span></div></div>
    <div class="summary-metrics">
      <div class="metric"><span class="muted">${ratioLabel}</span><b>${f(ratio)}</b><small>${ratio===null||ratio===undefined?'-':f(ratio-100)}%</small></div>
      <div class="metric"><span class="muted">RSI(14)</span><b>${f(t.rsi14)}</b><small>${t.state||'-'}</small></div>
      <div class="metric"><span class="muted">MACD 히스토그램</span><b>${f(t.macd_hist)}</b><small>Sigma ${f(t.sigma20)}</small></div>
    </div>
    <div class="summary-reading ${DASH.noteClass(zone)}"><strong>${x.headline||`현재 구간: ${zone}`}</strong><p>${reading}</p></div>
  </article>`;
};
DASH.opt=()=>({responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{labels:{color:'#c8d2e8',boxWidth:18}}},scales:{x:{ticks:{color:'#95a3bd',maxTicksLimit:8},grid:{color:'rgba(43,59,94,.3)'}},y:{ticks:{color:'#95a3bd'},grid:{color:'rgba(43,59,94,.3)'}}}});
DASH.line=(id,labels,sets,options)=>{const e=document.getElementById(id);if(e)new Chart(e,{type:'line',data:{labels,datasets:sets},options:options||DASH.opt()})};
DASH.s=(h,k)=>h.map(x=>x[k]??null);
DASH.setInterpretation=(id,a)=>{const el=document.getElementById(id);if(!el)return;const zone=a?.disparity_interpretation?.zone||'';el.className=`interpret note ${DASH.noteClass(zone)}`;el.innerHTML=DASH.interpretationHTML(a)};
DASH.interpolate=(rows,xKey,yKey,x)=>{if(!Array.isArray(rows)||!rows.length||x===null||x===undefined)return null;const sorted=[...rows].sort((a,b)=>a[xKey]-b[xKey]);if(x<=sorted[0][xKey])return Number(sorted[0][yKey]);if(x>=sorted[sorted.length-1][xKey])return Number(sorted[sorted.length-1][yKey]);for(let i=1;i<sorted.length;i++){const a=sorted[i-1],b=sorted[i];if(x<=b[xKey]){const t=(x-a[xKey])/(b[xKey]-a[xKey]);return Number(a[yKey])+t*(Number(b[yKey])-Number(a[yKey]))}}return null};
const quadrantPlugin={id:'quadrantBackground',beforeDraw(chart,args,o){if(!o?.enabled)return;const {ctx,chartArea,scales}=chart;if(!chartArea||!scales.x||!scales.y)return;const {left,right,top,bottom}=chartArea,x0=Math.min(right,Math.max(left,scales.x.getPixelForValue(0))),y0=Math.min(bottom,Math.max(top,scales.y.getPixelForValue(0)));ctx.save();ctx.fillStyle='rgba(255,150,80,.10)';ctx.fillRect(x0,top,right-x0,y0-top);ctx.fillStyle='rgba(255,220,90,.09)';ctx.fillRect(left,y0,x0-left,bottom-y0);ctx.fillStyle='rgba(111,168,255,.05)';ctx.fillRect(left,top,x0-left,y0-top);ctx.fillRect(x0,y0,right-x0,bottom-y0);ctx.fillStyle='#ffbd4a';ctx.font='700 13px system-ui';ctx.fillText('탐욕·추격 관찰',Math.max(x0+10,right-130),top+20);ctx.fillText('공포·투매 관찰',left+10,bottom-12);ctx.restore();}};
const pointLabelsPlugin={id:'pointLabels',afterDatasetsDraw(chart,args,o){if(!o?.enabled)return;const idx=o.datasetIndex??3,meta=chart.getDatasetMeta(idx),data=chart.data.datasets[idx]?.data||[],ctx=chart.ctx;ctx.save();ctx.font='700 12px system-ui';ctx.fillStyle='#ffbd4a';ctx.strokeStyle='rgba(8,16,31,.95)';ctx.lineWidth=4;meta.data.forEach((pt,i)=>{const label=data[i]?.label;if(!label)return;const x=pt.x+7,y=pt.y-8;ctx.strokeText(label,x,y);ctx.fillText(label,x,y)});ctx.restore();}};
Chart.register(quadrantPlugin,pointLabelsPlugin);
