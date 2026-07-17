#!/usr/bin/env python3
from __future__ import annotations

import json, math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'; DATA_DIR=DOCS/'data'; TEMPLATE=ROOT/'templates'/'index.template.html'
MANUAL=DATA_DIR/'manual_signals.json'; OUTPUT_JSON=DATA_DIR/'market_data.json'; OUTPUT_CSV=DATA_DIR/'market_history.csv'; OUTPUT_HTML=DOCS/'index.html'
SEOUL=timezone(timedelta(hours=9))

ASSETS={
 'KOSPI':{'name':'KOSPI','type':'index','pykrx':'1001','yf':'^KS11'},
 'KOSDAQ':{'name':'KOSDAQ','type':'index','pykrx':'2001','yf':'^KQ11'},
 'SAMSUNG':{'name':'삼성전자','type':'stock','pykrx':'005930','yf':'005930.KS'},
 'SKHYNIX':{'name':'SK하이닉스','type':'stock','pykrx':'000660','yf':'000660.KS'},
 'SOX':{'name':'SOX','type':'global_index','yf':'^SOX'},
 'NDX':{'name':'나스닥100','type':'global_index','yf':'^NDX'},
}


def cf(v:Any)->float|None:
 try:
  x=float(v)
  return None if math.isnan(x) or math.isinf(x) else round(x,4)
 except Exception:return None


def load_manual():
 try:return json.loads(MANUAL.read_text(encoding='utf-8'))
 except Exception:return {}


def yf_fetch(ticker,start,end):
 import yfinance as yf
 raw=yf.download(ticker,start=start,end=end,auto_adjust=False,progress=False)
 if raw is None or raw.empty: raise RuntimeError('yfinance empty')
 c=raw['Close']; c=c.iloc[:,0] if isinstance(c,pd.DataFrame) else c
 df=pd.DataFrame({'close':pd.to_numeric(c,errors='coerce')},index=pd.to_datetime(c.index))
 if 'Volume' in raw:
  v=raw['Volume']; v=v.iloc[:,0] if isinstance(v,pd.DataFrame) else v
  df['volume']=pd.to_numeric(v,errors='coerce')
 return df.dropna(subset=['close']).sort_index()


def pykrx_fetch(asset,start,end):
 from pykrx import stock
 if asset['type']=='index': raw=stock.get_index_ohlcv_by_date(start.replace('-',''),end.replace('-',''),asset['pykrx'])
 else: raw=stock.get_market_ohlcv_by_date(start.replace('-',''),end.replace('-',''),asset['pykrx'])
 if raw is None or raw.empty: raise RuntimeError('pykrx empty')
 df=pd.DataFrame(index=pd.to_datetime(raw.index)); df['close']=pd.to_numeric(raw['종가'],errors='coerce')
 if '거래량' in raw: df['volume']=pd.to_numeric(raw['거래량'],errors='coerce')
 return df.dropna(subset=['close']).sort_index()


def fetch_asset(asset,start,end):
 if asset['type'] in ('index','stock'):
  try:return pykrx_fetch(asset,start,end),'KRX(pykrx)'
  except Exception:pass
 return yf_fetch(asset['yf'],start,end),'Yahoo Finance fallback'


def fetch_vkospi(start,end):
 from pykrx import stock
 candidates=[]
 for market in ['KOSPI','KOSDAQ','KRX','테마']:
  try:
   for t in stock.get_index_ticker_list(market=market):
    n=stock.get_index_ticker_name(t)
    if 'VKOSPI' in n.upper() or '변동성' in n: candidates.append((t,n))
  except Exception:pass
 for ticker,name in candidates:
  try:
   raw=stock.get_index_ohlcv_by_date(start.replace('-',''),end.replace('-',''),ticker)
   if raw is not None and not raw.empty:
    return pd.DataFrame({'close':pd.to_numeric(raw['종가'],errors='coerce')},index=pd.to_datetime(raw.index)).dropna(),f'KRX {name}'
  except Exception:pass
 raise RuntimeError('VKOSPI ticker not resolved')


def percentile(series,window=756):
 s=series.dropna().tail(window)
 return cf(s.rank(pct=True).iloc[-1]*100) if len(s)>=20 else None


def enrich(df):
 out=df.copy()
 for w in (5,20,30,50,60,100,120,200): out[f'sma{w}']=out.close.rolling(w).mean()
 for w in (30,50,60,100,120,200): out[f'ratio{w}']=out.close/out[f'sma{w}']*100
 out['drawdown']=out.close/out.close.rolling(252,min_periods=20).max()*100-100
 return out


def metrics(key,df,source):
 out=enrich(df); last=out.iloc[-1]; prev=out.iloc[-2] if len(out)>1 else last
 s=out.close.tail(252); dd=s/s.cummax()*100-100
 m={'name':ASSETS.get(key,{'name':key})['name'],'type':ASSETS.get(key,{'type':'index'})['type'],'date':out.index[-1].strftime('%Y-%m-%d'),'source':source,'close':cf(last.close),'change_pct':cf((last.close/prev.close-1)*100),'current_drawdown_pct':cf(dd.iloc[-1]),'mdd_252_pct':cf(dd.min())}
 for w in (30,50,60,100,120,200):
  m[f'sma{w}']=cf(last.get(f'sma{w}')); m[f'ratio{w}']=cf(last.get(f'ratio{w}')); m[f'dev{w}']=cf(last.get(f'ratio{w}')-100) if pd.notna(last.get(f'ratio{w}')) else None; m[f'ratio{w}_percentile_3y']=percentile(out[f'ratio{w}'])
 c=out.close.tail(3); m['rebound_3d']=bool(len(c)>=3 and c.iloc[-1]>c.iloc[0] and c.iloc[-1]>c.min())
 cols=['close','sma30','sma50','sma60','sma100','sma120','sma200','ratio30','ratio50','ratio60','ratio100','ratio120','ratio200','drawdown']
 m['history']=[{'date':i.strftime('%Y-%m-%d'),**{c:cf(r.get(c)) for c in cols}} for i,r in out.tail(520).iterrows()]
 return m,out


def event_study(out,threshold=-20):
 dd=out.close/out.close.rolling(252,min_periods=50).max()*100-100
 hits=[]; last_hit=-999
 for i in range(1,len(dd)):
  if dd.iloc[i]<=threshold and dd.iloc[i-1]>threshold and i-last_hit>60:
   row={'date':out.index[i].strftime('%Y-%m-%d')}
   for h in (5,20,60): row[f'r{h}']=cf((out.close.iloc[i+h]/out.close.iloc[i]-1)*100) if i+h<len(out) else None
   row['to_minus30']=bool(dd.iloc[i:min(i+61,len(dd))].min()<=-30); hits.append(row); last_hit=i
 valid=[x for x in hits if x['r60'] is not None]
 def stat(k,kind='mean'):
  a=[x[k] for x in valid if x[k] is not None]
  if not a:return None
  return cf(np.mean(a) if kind=='mean' else np.median(a))
 return {'sample_count':len(valid),'period_start':valid[0]['date'] if valid else None,'period_end':valid[-1]['date'] if valid else None,'avg_5d':stat('r5'),'avg_20d':stat('r20'),'avg_60d':stat('r60'),'median_5d':stat('r5','median'),'median_20d':stat('r20','median'),'median_60d':stat('r60','median'),'positive_5d_pct':cf(np.mean([x['r5']>0 for x in valid])*100) if valid else None,'positive_20d_pct':cf(np.mean([x['r20']>0 for x in valid])*100) if valid else None,'positive_60d_pct':cf(np.mean([x['r60']>0 for x in valid])*100) if valid else None,'transition_to_minus30_pct':cf(np.mean([x['to_minus30'] for x in valid])*100) if valid else None,'events':valid[-10:]}


def breadth(date,market):
 try:
  from pykrx import stock
  raw=stock.get_market_ohlcv_by_ticker(date.replace('-',''),market=market); r=pd.to_numeric(raw['등락률'],errors='coerce').dropna()
  a,d,z=int((r>0).sum()),int((r<0).sum()),int((r==0).sum())
  return {'advancers':a,'decliners':d,'unchanged':z,'ad_ratio':cf(a/d) if d else None}
 except Exception as e:return {'error':str(e),'advancers':None,'decliners':None,'unchanged':None,'ad_ratio':None}


def psychology(start,end,kospi):
 try:
  from pykrx import stock
  raw=stock.get_market_trading_value_by_date(start.replace('-',''),end.replace('-',''),'KOSPI')
  col=next(c for c in raw.columns if '개인' in str(c)); x=pd.to_numeric(raw[col],errors='coerce')/1e12
  kret=kospi.close.pct_change()*100; df=pd.concat([x.rename('individual_net_buy_trn'),kret.rename('kospi_return_pct')],axis=1).dropna().tail(180)
  slope,intercept=np.polyfit(df.iloc[:,0],df.iloc[:,1],1); pred=slope*df.iloc[-1,0]+intercept; resid=df.iloc[-1,1]-pred
  if df.iloc[-1,0]>0 and df.iloc[-1,1]<0: label='개인 저가매수·외국인 매도 우위: 청산 미완료 가능성'
  elif resid>1: label='개인 매수 대비 지수 반응이 강해 수급 개선 가능성'
  elif resid<-1: label='개인 매수에도 지수 반응이 약해 탐욕·물타기 위험'
  else: label='과거 회귀선 부근의 중립 수급'
  return {'points':[{'date':i.strftime('%Y-%m-%d'),'x':cf(r.iloc[0]),'y':cf(r.iloc[1])} for i,r in df.iterrows()],'slope':cf(slope),'intercept':cf(intercept),'latest_residual':cf(resid),'interpretation':label}
 except Exception as e:return {'points':[],'error':str(e),'interpretation':'개인 순매수 데이터 미산출'}


def vkospi_view(m):
 v=m.get('close'); p=m.get('ratio50_percentile_3y')
 if v is None:return 'VKOSPI 미산출'
 if v>=35:s='극단적 공포·강제청산 위험 구간'
 elif v>=25:s='고변동성 경계 구간'
 elif v>=18:s='불안 확대 구간'
 else:s='안정 구간'
 return f'{s}. 3년 백분위 {p:.1f}%' if p is not None else s


def ndx_view(m):
 r=m.get('ratio100')
 if r is None:return '100일선 미산출'
 if r<95:return '나스닥100이 100일선을 크게 하회: 글로벌 성장주 위험회피'
 if r<100:return '나스닥100이 100일선 아래: 반도체 반등 신뢰도 제한'
 if r<105:return '나스닥100이 100일선 부근 또는 소폭 상회: 중립'
 return '나스닥100이 100일선 위: 미국 성장주 추세는 유지'


def valuation(assets,manual):
 ref=manual.get('forward_valuation_reference',{}); out={'reference_date':ref.get('reference_date'),'source':ref.get('source'),'note':ref.get('note'),'rows':[]}
 for key,c in ref.get('companies',{}).items():
  price=assets.get(key,{}).get('close'); eps=c.get('eps',{}); row={'key':key,'name':c.get('name'),'price':price,'target_price':c.get('target_price')}
  for y in ('2026','2027','2028'): row[f'eps_{y}']=eps.get(y); row[f'per_{y}']=cf(price/eps[y]) if price and eps.get(y) else None
  p=row.get('per_2027')
  row['interpretation']='미산출' if p is None else ('강한 감익 우려가 반영된 초저PER' if p<6 else '저PER이나 EPS 하향과 호재 반응 확인 필요' if p<8 else '중립 밸류에이션' if p<10 else '높은 이익 지속 신뢰 반영')
  out['rows'].append(row)
 return out


def classify(asset):
 r=asset.get('ratio30') if asset.get('type')=='stock' else asset.get('ratio50'); dd=asset.get('current_drawdown_pct'); reb=asset.get('rebound_3d')
 score=(2 if dd is not None and dd<=-20 else 1 if dd is not None and dd<=-10 else 0)+(1 if r is not None and r<100 else 0)+(1 if reb else 0)
 if r is not None and r<90 and not reb:return '낙하 중·확인 필요',score
 if score>=4 and reb:return '반등 확인',score
 if score>=3:return '과매도 접근',score
 if r is not None and r<100:return '추세 훼손',score
 return '중립',score


def main():
 DATA_DIR.mkdir(parents=True,exist_ok=True); manual=load_manual(); enddt=datetime.now(SEOUL)+timedelta(days=1); startdt=enddt-timedelta(days=4000); start,end=startdt.strftime('%Y-%m-%d'),enddt.strftime('%Y-%m-%d')
 assets={}; frames={}; errors={}; studies={}
 for k,c in ASSETS.items():
  try:
   f,src=fetch_asset(c,start,end); frames[k]=f; assets[k],en=metrics(k,f,src); studies[k]=event_study(en); label,score=classify(assets[k]); assets[k]['signal']=label; assets[k]['score']=score
  except Exception as e:errors[k]=str(e)
 try:
  f,src=fetch_vkospi(start,end); frames['VKOSPI']=f; assets['VKOSPI'],en=metrics('VKOSPI',f,src); assets['VKOSPI']['name']='VKOSPI'; assets['VKOSPI']['type']='volatility'; assets['VKOSPI']['interpretation']=vkospi_view(assets['VKOSPI'])
 except Exception as e:errors['VKOSPI']=str(e)
 if 'NDX' in assets:assets['NDX']['interpretation']=ndx_view(assets['NDX'])
 if 'KOSPI' in assets:
  psy=psychology(start,end,frames['KOSPI']); latest=assets['KOSPI']['date']
 else:psy={'points':[],'interpretation':'미산출'}; latest=datetime.now(SEOUL).strftime('%Y-%m-%d')
 val=valuation(assets,manual)
 payload={'generated_at':datetime.now(SEOUL).isoformat(timespec='seconds'),'status':'ok' if assets else 'error','methodology':{'disparity_ratio':'현재가 ÷ 이동평균 × 100','deviation_pct':'이격도 지수 - 100','index_windows':[50,60,100,120,200],'stock_tactical_window':30,'drawdown_window':252},'assets':assets,'event_studies':studies,'market_psychology':psy,'valuation':val,'breadth':{'KOSPI':breadth(latest,'KOSPI'),'KOSDAQ':breadth(latest,'KOSDAQ')},'manual':manual,'errors':errors}
 OUTPUT_JSON.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
 rows=[]
 for k,a in assets.items():
  for h in a.get('history',[]): rows.append({'asset':k,**h})
 pd.DataFrame(rows).to_csv(OUTPUT_CSV,index=False,encoding='utf-8-sig')
 html=TEMPLATE.read_text(encoding='utf-8').replace('__EMBEDDED_DATA__',json.dumps(payload,ensure_ascii=False,separators=(',',':'))); OUTPUT_HTML.write_text(html,encoding='utf-8')
 print('dashboard updated')

if __name__=='__main__':main()
