import time
import pandas as pd
from scanner.upstox import load_nse_equities,historical_daily
from scanner.engine import analyze
from scanner.alerts import send,format_result

def run(limit=None):
    universe=load_nse_equities()
    if limit: universe=universe.head(limit)
    print(f'Scanning {len(universe)} NSE equities...')
    results=[]
    nifty_df=None
    for _,row in universe.iterrows():
        try:
            result=analyze(row.trading_symbol,historical_daily(row.instrument_key),nifty_df)
            if result:
                results.append(result)
                if result['buy']:send(format_result(result,'BUY'))
                elif result['candidate']:send(format_result(result,'CANDIDATE'))
        except Exception as exc: print(f"[{row.trading_symbol}] {exc}")
        time.sleep(0.05)
    out=pd.DataFrame(results)
    if not out.empty: out.to_csv('scan_results.csv',index=False)
    print(out[out.candidate].to_string(index=False) if not out.empty else 'No results')
    return out

if __name__=='__main__': run()
