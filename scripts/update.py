from pathlib import Path
import sys, time, json, warnings
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
warnings.filterwarnings('ignore', category=DeprecationWarning)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'snapshots'
OUT.mkdir(parents=True, exist_ok=True)
LOCK = OUT / 'refresh.lock'
def clean(s):
    s = pd.to_numeric(s, errors='coerce').dropna()
    idx = pd.DatetimeIndex(pd.to_datetime(s.index))
    if idx.tz is not None: idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep='last')].sort_index()
def get_series(block, ticker):
    c = block['Close'][ticker] if isinstance(block.columns, pd.MultiIndex) else block['Close']
    return clean(c)
def value(s, date):
    x = s[s.index <= date]
    return float(x.iloc[-1]) if len(x) else None
def period_return(s, date):
    p = value(s.iloc[:-1], date)
    return float(s.iloc[-1] / p - 1) if p else None
def metrics(s):
    a = pd.Timestamp(s.index[-1]); c = float(s.iloc[-1]); p = float(s.iloc[-2])
    monday = a - pd.DateOffset(days=int(a.weekday())); qmonth = ((a.month - 1) // 3) * 3 + 1
    return {'Close':c,'Today':c/p-1,'WTD':period_return(s,monday-pd.DateOffset(days=1)),'MTD':period_return(s,pd.Timestamp(a.year,a.month,1)-pd.DateOffset(days=1)),'QTD':period_return(s,pd.Timestamp(a.year,qmonth,1)-pd.DateOffset(days=1)),'YTD':period_return(s,pd.Timestamp(a.year,1,1)-pd.DateOffset(days=1)),'3Y Cum.':period_return(s,a-pd.DateOffset(years=3)),'5Y Cum.':period_return(s,a-pd.DateOffset(years=5)),'10Y Cum.':period_return(s,a-pd.DateOffset(years=10))}
def trailing_yield(ticker, anchor=None):
    h = yf.Ticker(ticker).history(period='max', auto_adjust=False, actions=True, timeout=15)
    if h.empty: return None
    idx = pd.DatetimeIndex(pd.to_datetime(h.index))
    if idx.tz is not None: idx = idx.tz_localize(None)
    h.index = idx
    a = pd.Timestamp(anchor) if anchor is not None else pd.Timestamp(h.index[-1]); x = h[h.index <= a]
    return float(x.loc[x.index > a-pd.DateOffset(years=1),'Dividends'].sum()/x['Close'].iloc[-1]) if len(x) else None
def main():
    if LOCK.exists(): raise SystemExit('Refresh already running.')
    LOCK.write_text(datetime.now(timezone.utc).isoformat(), encoding='utf-8'); start=time.time()
    try:
        mp = pd.read_csv(ROOT/'data/source_mappings.csv')
        mp = mp[mp['Enabled'].astype(str).str.lower().isin(['true','1','yes'])]
        ticks = sorted(set(mp['Symbol'].dropna().tolist()+['^VIX']))
        block = yf.download(ticks, period='max', auto_adjust=False, actions=True, progress=False, threads=True, timeout=45)
        snap={'errors':[]}
        for section,key in [('Equity Indices','equities'),('Sector Performance','sectors'),('Fixed Income','fixed_income'),('Commodities','commodities'),('Global Markets & Currency Trends','global_markets')]:
            output=[]
            for _,r in mp[mp['Section']==section].iterrows():
                try:
                    z=metrics(get_series(block,r['Symbol'])); z['Description']=r['Display Name']
                    if section=='Fixed Income': z['Yield']=trailing_yield(r['Symbol']); z.pop('Close',None)
                except Exception as exc:
                    z={'Description':r['Display Name']}; snap['errors'].append(f"{r['Display Name']}: {exc}")
                output.append(z)
            snap[key]=output
        risk=[]
        for name,ticker,is_yield in [('S&P 500','^GSPC',False),('10-Year Treasury Yield','^TNX',True),('U.S. Dollar Index','DX-Y.NYB',False),('Gold','GC=F',False),('Bitcoin','BTC-USD',False),('VIX','^VIX',False)]:
            x=get_series(block,ticker); risk.append({'Asset':name,'Current':float(x.iloc[-1]),'Change':float(x.iloc[-1]-x.iloc[-2]) if is_yield else float(x.iloc[-1]/x.iloc[-2]-1),'Yield':is_yield})
        snap['risk']=risk; curve={}
        for _,r in mp[mp['Section']=='Treasury Yield Curve'].iterrows():
            try:
                x=get_series(block,r['Symbol']); a=x.index[-1]; direct=r['Kind']=='direct'
                curve[r['Display Name']]={'Current':float(x.iloc[-1]) if direct else trailing_yield(r['Symbol'],a)*100,'1 Month Prior':value(x,a-pd.DateOffset(months=1)) if direct else trailing_yield(r['Symbol'],a-pd.DateOffset(months=1))*100,'1 Year Prior':value(x,a-pd.DateOffset(years=1)) if direct else trailing_yield(r['Symbol'],a-pd.DateOffset(years=1))*100}
            except Exception as exc: snap['errors'].append(f"Curve {r['Display Name']}: {exc}")
        snap['curve']=curve; now=datetime.now(timezone.utc)
        snap.update({'generated_at':now.isoformat(),'snapshot_id':now.strftime('%Y-%m-%d_%H%M'),'duration':round(time.time()-start,1),'status':'Success' if not snap['errors'] else 'Completed with source notes'})
        tmp=OUT/'current.tmp'; tmp.write_text(json.dumps(snap,indent=2),encoding='utf-8'); tmp.replace(OUT/'current.json')
        print('Refresh complete')
    finally: LOCK.unlink(missing_ok=True)
if __name__=='__main__': main()
