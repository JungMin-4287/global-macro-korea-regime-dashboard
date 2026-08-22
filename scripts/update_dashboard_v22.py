#!/usr/bin/env python3
"""v22: macro stagflation/recession regime + Korea index inverse hedge overlay."""
from __future__ import annotations
import json, math, runpy
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[1]; V21=Path(__file__).with_name('update_dashboard_v21.py')
JSON=ROOT/'docs/data/market_data.json'; HTML=ROOT/'docs/index.html'; HIST=ROOT/'docs/data/macro_regime_history.csv'; KST=ZoneInfo('Asia/Seoul')
H={'User-Agent':'Mozilla/5.0 Chrome/124 Safari/537.36'}
Y={'gold':('GC=F','Gold'),'copper':('HG=F','Copper'),'dxy':('DX-Y.NYB','DXY'),'vix':('^VIX','VIX'),'oil':('CL=F','WTI')}
F={'bei10':('T10YIE','10Y BEI'),'real30':('DFII30','30Y real yield'),'hy':('BAMLH0A0HYM2','HY OAS')}

def num(x,d=3):
    try:
        x=float(x); return round(x,d) if math.isfinite(x) else None
    except: return None

def pct(s,n):
    s=pd.to_numeric(s,errors='coerce').dropna(); return num((s.iloc[-1]/s.iloc[-n-1]-1)*100) if len(s)>n and s.iloc[-n-1] else None

def chg(s,n):
    s=pd.to_numeric(s,errors='coerce').dropna(); return num(s.iloc[-1]-s.iloc[-n-1],4) if len(s)>n else None

def yahoo(t):
    now=pd.Timestamp.now(tz='UTC'); start=now-pd.Timedelta(days=180)
    u=f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(t,safe='')}?period1={int(start.timestamp())}&period2={int((now+pd.Timedelta(days=1)).timestamp())}&interval=1d"
    r=requests.get(u,headers=H,timeout=(5,15)); r.raise_for_status(); z=((r.json().get('chart') or {}).get('result') or [None])[0]
    ts=z.get('timestamp') or []; c=((((z.get('indicators') or {}).get('quote') or [{}])[0]).get('close') or [])
    s=pd.Series(pd.to_numeric(c,errors='coerce'),index=pd.to_datetime(ts,unit='s',utc=True).tz_convert(None).normalize()).dropna().sort_index()
    return s.loc[~s.index.duplicated(keep='last')]

def fred(i):
    r=requests.get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={quote(i)}',headers=H,timeout=(5,20)); r.raise_for_status(); f=pd.read_csv(StringIO(r.text))
    f['DATE']=pd.to_datetime(f['DATE'],errors='coerce'); f[i]=pd.to_numeric(f[i],errors='coerce'); return f.dropna().set_index('DATE')[i].tail(260)

def snap(s,label,src):
    return {'label':label,'value':num(s.iloc[-1]),'date':s.index[-1].date().isoformat(),'p5':pct(s,5),'p10':pct(s,10),'p20':pct(s,20),'d10':chg(s,10),'d20':chg(s,20),'source':src}

def build(old):
    S={}; M={}; err={}
    for k,(t,l) in Y.items():
        try:S[k]=yahoo(t); M[k]=snap(S[k],l,f'Yahoo {t}')
        except Exception as e:err[k]=str(e)
    for k,(i,l) in F.items():
        try:S[k]=fred(i); M[k]=snap(S[k],l,f'FRED {i}')
        except Exception as e:err[k]=str(e)
    if 'gold' in S and 'copper' in S:
        q=pd.concat([S['gold'],S['copper']],axis=1).dropna(); S['gc']=(q.iloc[:,0]/q.iloc[:,1]).dropna(); M['gc']=snap(S['gc'],'Gold/Copper','derived')
    if len(M)<6 and old.get('macro_regime_hedge'):
        b=dict(old['macro_regime_hedge']); b['stale']=True; b['refresh_error']=err; return b
    g20=M.get('gold',{}).get('p20'); c20=M.get('copper',{}).get('p20'); gc20=M.get('gc',{}).get('p20'); dx20=M.get('dxy',{}).get('p20')
    o10=M.get('oil',{}).get('p10'); o20=M.get('oil',{}).get('p20'); bei=num((M.get('bei10',{}).get('d10') or 0)*100,1) if M.get('bei10',{}).get('d10') is not None else None
    ry=M.get('real30',{}).get('value'); ry20=M.get('real30',{}).get('d20'); hy=M.get('hy',{}).get('value'); hy20=M.get('hy',{}).get('d20'); vx=M.get('vix',{}).get('value'); vx5=M.get('vix',{}).get('p5')
    ge=lambda v,x:v is not None and v>=x; le=lambda v,x:v is not None and v<=x
    inf=sum([ge(bei,5),ge(o10,5),ge(o20,8)]); stag=sum([ge(gc20,3),ge(g20,3),g20 is not None and c20 is not None and c20<g20]); dur=sum([ge(ry,2.5),ge(ry20,.10)])
    cred=sum([ge(hy,4),ge(hy20,.40),ge(vx,25),ge(vx5,20)]); brk=sum([le(c20,-5),le(o20,-5),ge(gc20,6)]); refl=sum([ge(c20,3),ge(o20,3),ge(bei,3),gc20 is not None and gc20<=2])
    if cred>=2 and brk>=1:r,L,kd,kp,tot,a='Credit/Recession',4,'10~15%','5~10%','15~25%','KOSDAQ·KOSPI 인버스 확대. 산업금속·정유 베타 축소와 금/현금·장기채 전환 조건 확인'
    elif inf>=2 and stag>=2 and (dur>=1 or cred>=1):r,L,kd,kp,tot,a='Deep Stagflation',3,'10~15%','5~10%','15~25%','KOSDAQ 인버스 중심 + KOSPI 인버스 추가. 수요파괴와 신용스프레드 감시'
    elif inf>=1 and stag>=2:r,L,kd,kp,tot,a='Early Stagflation',2,'5~10%','0~5%','5~15%','KOSDAQ150 인버스 1차 헤지. KOSPI 인버스는 HY OAS·VIX 악화 확인 후 추가'
    elif refl>=3 and cred==0:r,L,kd,kp,tot,a='Reflation',1,'0~5%','0%','0~5%','인버스 최소화. 실물자산 롱 유지, Gold/Copper 상승 전환 감시'
    elif inf==0 and cred==0 and le(o20,0) and le(bei,0):r,L,kd,kp,tot,a='Disinflation / Pivot Watch',0,'0~5%','0~5%','0~10%','인버스 축소. 실질금리 하락+신용 안정이면 장기채/성장주 반등 점검'
    else:r,L,kd,kp,tot,a='Transition / Mixed',1,'0~5%','0~5%','0~10%','소규모 헤지만 유지. Gold/Copper·BEI·HY OAS·VIX 동시 방향 확인'
    d={'bei10_10d_bp':bei,'gold_copper_20d_pct':gc20,'gold_20d_pct':g20,'copper_20d_pct':c20,'dxy_20d_pct':dx20,'oil_20d_pct':o20,'real30_pct':ry,'hy_oas_pct':hy,'vix':vx}
    return {'generated_at':datetime.now(KST).isoformat(timespec='seconds'),'regime':r,'hedge_level':L,'hedge':{'KODEX 코스닥150선물인버스(251340)':kd,'KODEX 인버스(114800)':kp,'총 지수헤지':tot,'2X':'자동 편입 금지; Credit/Recession 확정 후 단기 전술용만 검토'},'action':a,'metrics':M,'derived':d,'scorecard':{'inflation':inf,'stag_rotation':stag,'duration':dur,'credit':cred,'growth_break':brk,'reflation':refl},'coverage':{'available':len(M),'errors':err},'stale':False}

def history(b):
    row={'date':datetime.now(KST).date().isoformat(),'generated_at':b.get('generated_at'),'regime':b.get('regime'),'hedge_level':b.get('hedge_level'),'total_hedge':b.get('hedge',{}).get('총 지수헤지'),**b.get('derived',{})}
    try:h=pd.read_csv(HIST)
    except:h=pd.DataFrame()
    h=pd.concat([h,pd.DataFrame([row])],ignore_index=True).drop_duplicates('date',keep='last').sort_values('date'); h.tail(1000).to_csv(HIST,index=False,encoding='utf-8-sig')

def inject():
    t=HTML.read_text(encoding='utf-8'); marker='<h2 class="section-title">시장 심리와 외부 환경</h2>'
    sec='''<h2 class="section-title">매크로 레짐 · 인버스 헤지</h2><section class="grid" id="macroRegimeSection"><article class="card span4"><div class="name">현재 레짐</div><div class="value" id="mrR">-</div><span class="badge neutral" id="mrL">-</span><div class="note" id="mrA" style="margin-top:12px"></div></article><article class="card span4"><h2>헤지 범위</h2><div class="metrics"><div class="metric"><span class="muted">KOSDAQ</span><b id="mrKQ">-</b></div><div class="metric"><span class="muted">KOSPI</span><b id="mrKP">-</b></div><div class="metric"><span class="muted">총 헤지</span><b id="mrT">-</b></div><div class="metric"><span class="muted">2X</span><b>자동편입 금지</b></div></div></article><article class="card span4"><h2>판별값</h2><div class="metrics"><div class="metric"><span class="muted">Gold/Copper 20D</span><b id="mrGC">-</b></div><div class="metric"><span class="muted">BEI 10D</span><b id="mrB">-</b></div><div class="metric"><span class="muted">30Y 실질</span><b id="mrY">-</b></div><div class="metric"><span class="muted">HY OAS</span><b id="mrH">-</b></div><div class="metric"><span class="muted">DXY 20D</span><b id="mrD">-</b></div><div class="metric"><span class="muted">VIX</span><b id="mrV">-</b></div></div></article></section>'''
    if marker in t and 'macroRegimeSection' not in t:t=t.replace(marker,sec+marker,1)
    js='''<script>(async()=>{try{let d=await(await fetch('data/market_data.json?mr='+Date.now(),{cache:'no-store'})).json(),m=d.macro_regime_hedge||{},x=m.derived||{},h=m.hedge||{},q=(i,v)=>{let e=document.getElementById(i);if(e)e.textContent=v??'-'},n=(v,s='',d=2)=>v==null?'-':Number(v).toLocaleString('ko-KR',{maximumFractionDigits:d})+s;q('mrR',m.regime);q('mrL','Hedge '+(m.hedge_level??'-')+'/4');q('mrA',m.action);q('mrKQ',h['KODEX 코스닥150선물인버스(251340)']);q('mrKP',h['KODEX 인버스(114800)']);q('mrT',h['총 지수헤지']);q('mrGC',n(x.gold_copper_20d_pct,'%'));q('mrB',n(x.bei10_10d_bp,'bp',1));q('mrY',n(x.real30_pct,'%'));q('mrH',n(x.hy_oas_pct,'%'));q('mrD',n(x.dxy_20d_pct,'%'));q('mrV',n(x.vix,'',1));let b=document.getElementById('mrL');if(b)b.className='badge '+((m.hedge_level||0)>=4?'bad':(m.hedge_level||0)>=2?'warn':'good')}catch(e){console.warn('macroRegime',e)}})();</script>'''
    if "console.warn('macroRegime'" not in t:t=t.replace('</body>',js+'</body>',1)
    HTML.write_text(t,encoding='utf-8')

def main():
    try:old=json.loads(JSON.read_text(encoding='utf-8'))
    except:old={}
    runpy.run_path(str(V21),run_name='__main__'); p=json.loads(JSON.read_text(encoding='utf-8')); b=build(old); p['macro_regime_hedge']=b; JSON.write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8'); history(b); inject(); print('v22',b.get('regime'),b.get('hedge_level'))
if __name__=='__main__':main()
