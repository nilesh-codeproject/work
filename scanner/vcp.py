import numpy as np
from config import settings
from scanner.indicators import atr

def detect_vcp(df):
    empty={'true_vcp':False,'breakout':False,'contractions':0,'pivot':np.nan,'tightness':np.nan,
           'volume_ratio':np.nan,'atr_ratio':np.nan,'quality_score':0,'reasons':['insufficient_data']}
    if len(df)<settings.VCP_BASE_LEN+settings.VCP_SEGMENT*2+10:return empty
    x=df.copy(); n=settings.VCP_SEGMENT
    x['range_pct']=(x['high']-x['low'])/x['close']*100
    x['atr14']=atr(x,14)
    s1=x['range_pct'].iloc[-(n*2+1):-(n+1)].mean()
    s2=x['range_pct'].iloc[-(n+1):-1].mean()
    s3=x['range_pct'].iloc[-n:].mean()
    c1=np.isfinite(s1) and np.isfinite(s2) and s2<s1*settings.VCP_RANGE_SHRINK
    c2=np.isfinite(s2) and np.isfinite(s3) and s3<s2*settings.VCP_RANGE_SHRINK
    contractions=int(c1)+int(c2)
    base_atr=x['atr14'].iloc[-settings.VCP_BASE_LEN:].mean()
    recent_atr=x['atr14'].iloc[-n:].mean()
    ar=recent_atr/base_atr if base_atr>0 else np.nan
    base_vol=x['volume'].iloc[-20:].mean()
    vr=x['volume'].iloc[-n:].mean()/base_vol if base_vol>0 else np.nan
    fh=x['high'].iloc[-n:].max(); fl=x['low'].iloc[-n:].min(); fc=x['close'].iloc[-1]
    tight=(fh-fl)/fc*100 if fc else np.nan
    bh=x['high'].iloc[-settings.VCP_BASE_LEN-1:-1].max()
    bl=x['low'].iloc[-settings.VCP_BASE_LEN-1:-1].min()
    w=bh-bl
    upper=w>0 and (fc-bl)/w>=settings.VCP_UPPER_BASE_RATIO
    checks=[
        ('2_contractions',contractions>=2),
        ('range_shrink',c1 and c2),
        ('atr_contracts',np.isfinite(ar) and ar<settings.VCP_ATR_RATIO),
        ('volume_dryup',np.isfinite(vr) and vr<settings.VCP_VOLUME_RATIO),
        ('tight_final',np.isfinite(tight) and tight<=settings.VCP_MAX_TIGHTNESS),
        ('upper_base',upper)
    ]
    score=sum(bool(v) for _,v in checks)
    reasons=[name for name,ok in checks if not ok]
    quality=score>=settings.VCP_MIN_QUALITY_SCORE
    breakout=quality and fc>=bh*(1+settings.BREAKOUT_BUFFER_PCT/100)
    return {'true_vcp':bool(quality),'breakout':bool(breakout),'contractions':contractions,'pivot':float(bh),
            'tightness':float(tight),'volume_ratio':float(vr),'atr_ratio':float(ar),
            'quality_score':score,'reasons':reasons}
