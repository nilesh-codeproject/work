import numpy as np
from config import settings
from scanner.indicators import atr

def detect_vcp(df):
    if len(df)<settings.VCP_BASE_LEN+settings.VCP_SEGMENT*2+10:
        return {'true_vcp':False,'breakout':False,'contractions':0,'pivot':np.nan,'tightness':np.nan}
    x=df.copy(); n=settings.VCP_SEGMENT
    x['range_pct']=(x['high']-x['low'])/x['close']*100; x['atr14']=atr(x,14)
    s1=x['range_pct'].iloc[-(n*2+1):-(n+1)].mean(); s2=x['range_pct'].iloc[-(n+1):-1].mean(); s3=x['range_pct'].iloc[-n:].mean()
    c1=np.isfinite(s1) and np.isfinite(s2) and s2<s1*settings.VCP_RANGE_SHRINK
    c2=np.isfinite(s2) and np.isfinite(s3) and s3<s2*settings.VCP_RANGE_SHRINK
    contractions=int(c1)+int(c2)
    ar=x['atr14'].iloc[-n:].mean()/x['atr14'].iloc[-settings.VCP_BASE_LEN:].mean()
    vr=x['volume'].iloc[-n:].mean()/x['volume'].iloc[-20:].mean()
    fh=x['high'].iloc[-n:].max(); fl=x['low'].iloc[-n:].min(); fc=x['close'].iloc[-1]
    tight=(fh-fl)/fc*100
    bh=x['high'].iloc[-settings.VCP_BASE_LEN-1:-1].max(); bl=x['low'].iloc[-settings.VCP_BASE_LEN-1:-1].min(); w=bh-bl
    upper=w>0 and (fc-bl)/w>=settings.VCP_UPPER_BASE_RATIO
    ok=contractions>=settings.VCP_MIN_CONTRACTIONS and np.isfinite(ar) and ar<settings.VCP_ATR_RATIO and np.isfinite(vr) and vr<settings.VCP_VOLUME_RATIO and tight<=settings.VCP_MAX_TIGHTNESS and upper
    return {'true_vcp':bool(ok),'breakout':bool(ok and fc>=bh*(1+settings.BREAKOUT_BUFFER_PCT/100)),'contractions':contractions,'pivot':float(bh),'tightness':float(tight),'volume_ratio':float(vr),'atr_ratio':float(ar)}
