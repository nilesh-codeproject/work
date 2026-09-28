import pandas as pd
from scanner.upstox import load_nse_equities,find_nifty500_key,historical_daily,historical_many
from scanner.engine import analyze
from scanner.alerts import send,format_result

def run(limit=None):
    universe=load_nse_equities()
    if limit: universe=universe.head(limit)
    print(f'Scanning {len(universe)} NSE equities...')
    nifty_key=find_nifty500_key()
    nifty_df=historical_daily(nifty_key,years=2)
    print(f'Nifty 500 benchmark: {nifty_key}, {len(nifty_df)} daily bars')
    results=[]
    data=historical_many(universe,years=2,max_workers=12)
    for _,row in universe.iterrows():
        symbol=row.trading_symbol
        _,df,error=data.get(row.instrument_key,(symbol,pd.DataFrame(),'missing'))
        if error:
            print(f'[{symbol}] {error}')
            continue
        try:
            result=analyze(symbol,df,nifty_df)
            if result:
                results.append(result)
                if result['buy']: send(format_result(result,'BUY'))
                elif result['candidate']: send(format_result(result,'CANDIDATE'))
        except Exception as exc:
            print(f'[{symbol}] {exc}')
    out=pd.DataFrame(results)
    if not out.empty:
        out=out.sort_values(['buy','candidate','vcp_quality','score'],ascending=False)
        out.to_csv('scan_results.csv',index=False)
        print('\nTop candidates:')
        print(out[out.candidate].head(30).to_string(index=False))
        print(f'\nBUY={int(out.buy.sum())} CANDIDATE={int(out.candidate.sum())} VCP={int(out.vcp.sum())} VCP_BREAKOUT={int(out.vcp_breakout.sum())}')
    else:
        print('No results')
    return out

if __name__=='__main__': run()
