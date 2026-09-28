import gzip,json,time,requests,pandas as pd
from datetime import date,timedelta
from concurrent.futures import ThreadPoolExecutor,as_completed
from threading import Lock
from config import settings

BASE='https://api.upstox.com'
RETRY_STATUS={429,500,502,503,504}

class RateLimiter:
    def __init__(self,per_minute):
        self.interval=60.0/per_minute
        self.lock=Lock()
        self.next_time=0.0

    def wait(self):
        with self.lock:
            now=time.monotonic()
            if now<self.next_time:
                time.sleep(self.next_time-now)
                now=time.monotonic()
            self.next_time=now+self.interval

rate_limiter=RateLimiter(settings.UPSTOX_REQUESTS_PER_MINUTE)

def headers():
    if not settings.UPSTOX_ACCESS_TOKEN:
        raise RuntimeError('UPSTOX_ACCESS_TOKEN is not configured.')
    return {'Authorization':f'Bearer {settings.UPSTOX_ACCESS_TOKEN}','Accept':'application/json'}

def _request_json(url,timeout=None,retries=None):
    timeout=timeout or settings.UPSTOX_REQUEST_TIMEOUT
    retries=settings.UPSTOX_MAX_RETRIES if retries is None else retries
    last=None
    for attempt in range(retries+1):
        rate_limiter.wait()
        try:
            r=requests.get(url,headers=headers(),timeout=timeout)
            if r.status_code in RETRY_STATUS:
                last=RuntimeError(f'HTTP {r.status_code}')
                if attempt>=retries:
                    raise last
                retry_after=r.headers.get('Retry-After')
                delay=float(retry_after) if retry_after else 2.0
                time.sleep(min(delay,5.0))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as exc:
            last=exc
            if attempt>=retries:
                raise
            time.sleep(1.0)
    raise last or RuntimeError('request failed')

def load_instruments():
    url='https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'
    r=requests.get(url,timeout=60)
    r.raise_for_status()
    return json.loads(gzip.decompress(r.content))

def load_nse_equities():
    data=load_instruments()
    rows=[{'instrument_key':x.get('instrument_key'),'trading_symbol':x.get('trading_symbol')}
          for x in data if x.get('segment')=='NSE_EQ'
          and x.get('instrument_type')=='EQ'
          and x.get('security_type','NORMAL')=='NORMAL']
    return pd.DataFrame(rows).dropna(subset=['instrument_key']).drop_duplicates('instrument_key').head(settings.MAX_UNIVERSE)

def find_nifty500_key():
    data=load_instruments()
    candidates=[x for x in data if x.get('segment')=='NSE_INDEX'
                and str(x.get('trading_symbol','')).upper() in {'NIFTY 500','NIFTY500'}]
    if not candidates:
        raise RuntimeError('Nifty 500 index instrument was not found in the Upstox instrument master.')
    return candidates[0].get('instrument_key')

def historical_daily(key,years=2):
    end=date.today()
    start=end-timedelta(days=365*years)
    url=f'{BASE}/v3/historical-candle/{key}/days/1/{end}/{start}'
    payload=_request_json(url)
    candles=payload.get('data',{}).get('candles',[])
    if not candles:
        return pd.DataFrame()
    df=pd.DataFrame(candles,columns=['timestamp','open','high','low','close','volume','oi'])
    df['timestamp']=pd.to_datetime(df['timestamp'])
    for col in ['open','high','low','close','volume']:
        df[col]=pd.to_numeric(df[col],errors='coerce')
    return df.sort_values('timestamp').reset_index(drop=True)

def historical_many(rows,years=2,max_workers=None):
    results={}
    workers=max_workers or settings.UPSTOX_MAX_WORKERS
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(historical_daily,row.instrument_key,years): row for _,row in rows.iterrows()}
        for future in as_completed(futures):
            row=futures[future]
            try:
                results[row.instrument_key]=(row.trading_symbol,future.result(),None)
            except Exception as exc:
                results[row.instrument_key]=(row.trading_symbol,pd.DataFrame(),str(exc))
    return results
