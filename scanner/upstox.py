import gzip,json,requests,pandas as pd
from datetime import date,timedelta
from config import settings
BASE='https://api.upstox.com'
INSTRUMENT_URL='https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz'

def headers():
    if not settings.UPSTOX_ACCESS_TOKEN: raise RuntimeError('UPSTOX_ACCESS_TOKEN is not configured.')
    return {'Authorization':f'Bearer {settings.UPSTOX_ACCESS_TOKEN}','Accept':'application/json'}

def load_instruments():
    r=requests.get(INSTRUMENT_URL,timeout=60); r.raise_for_status()
    return json.loads(gzip.decompress(r.content))

def load_nse_equities():
    data=load_instruments()
    rows=[{'instrument_key':x.get('instrument_key'),'trading_symbol':x.get('trading_symbol')}
          for x in data if x.get('segment')=='NSE_EQ' and x.get('instrument_type')=='EQ' and x.get('security_type','NORMAL')=='NORMAL']
    return pd.DataFrame(rows).dropna(subset=['instrument_key']).drop_duplicates('instrument_key').head(settings.MAX_UNIVERSE)

def find_index_key(data, names):
    wanted={n.strip().upper() for n in names}
    for x in data:
        if x.get('segment')=='NSE_INDEX' and str(x.get('trading_symbol','')).strip().upper() in wanted:
            return x.get('instrument_key')
    return None

def nifty500_key():
    return find_index_key(load_instruments(), ['NIFTY 500','NIFTY500'])

def historical_daily(key, years=2):
    end=date.today(); start=end-timedelta(days=365*years)
    url=f'{BASE}/v3/historical-candle/{key}/days/1/{end}/{start}'
    r=requests.get(url,headers=headers(),timeout=30); r.raise_for_status()
    c=r.json().get('data',{}).get('candles',[])
    if not c:return pd.DataFrame()
    df=pd.DataFrame(c,columns=['timestamp','open','high','low','close','volume','oi'])
    df['timestamp']=pd.to_datetime(df['timestamp'])
    for col in ['open','high','low','close','volume']: df[col]=pd.to_numeric(df[col],errors='coerce')
    return df.sort_values('timestamp').reset_index(drop=True)

def batched_quotes(keys):
    rows={}
    for i in range(0,len(keys),500):
        batch=keys[i:i+500]
        url=f'{BASE}/v3/market-quote/quotes'
        r=requests.get(url,headers=headers(),params={'instrument_key':','.join(batch)},timeout=30)
        r.raise_for_status()
        rows.update(r.json().get('data',{}))
    return rows
