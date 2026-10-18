from pathlib import Path
import pandas as pd,numpy as np,json,hashlib
ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
BASE=Path(__file__).resolve().parent
B2=ROOT/'outputs/Manuscript_Execution_20261006_b02_060919Z/batch02_coverage_hourly'
F=ROOT/'outputs/TomTom_Core_Freeze_20261004'
checks=[]
def check(name,condition,detail=None):
    checks.append(dict(check=name,passed=bool(condition),detail=detail))
    assert condition,(name,detail)
t=pd.read_csv(F/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv')
t['slot']=pd.to_datetime(t.interval_timestamp_local)
daily=t.groupby(t.slot.dt.date).size().to_numpy()
d=pd.read_csv(B2/'coverage/DAILY_COVERAGE.csv')
check('daily_counts_from_frozen',np.array_equal(daily,d.observed_records))
check('daily_reference_denominators',np.allclose(d.panel_coverage_pct,daily/4896*100) and np.allclose(d.typical_batch_reference_pct,daily/4032*100))
n=pd.read_csv(B2/'coverage/NODE_COVERAGE.csv')
nc=t.groupby('node_id').size()
check('node_missingness_from_frozen',np.allclose(n.set_index('node_id').loc[nc.index,'missing_pct'],100*(2304-nc)/2304))
check('node_extrema',n.loc[n.missing_pct.idxmin(),'node_id']=='N016' and n.loc[n.missing_pct.idxmax(),'node_id']=='N028')
t['hour']=t.slot.dt.floor('h')
nh=t.groupby(['node_id','hour']).current_speed_kmh.agg(['count','mean']).reset_index()
q=nh[nh['count']>=3].copy();q['clock']=q.hour.dt.hour
nc=q.groupby(['node_id','clock'])['mean'].agg(['size','mean','std'])
saved=pd.read_csv(B2/'hourly/NODE_CLOCK_VARIABILITY.csv').set_index(['node_id','clock_hour_local'])
check('node_clock_mean_sd_dates',np.allclose(nc['mean'],saved.loc[nc.index,'mean_speed_kmh']) and np.allclose(nc['std'],saved.loc[nc.index,'sample_sd_kmh']) and np.array_equal(nc['size'],saved.loc[nc.index,'date_count']))
o=q.groupby('hour')['mean'].agg(['size','mean']);o=o[o['size']>=41]
di=o.groupby(o.index.hour)['mean'].agg(['size','mean',lambda s:s.quantile(.1),lambda s:s.quantile(.9)])
saved_di=pd.read_csv(B2/'hourly/DIURNAL_PRIMARY.csv').set_index('clock_hour_local')
check('overall_diurnal_from_frozen',np.allclose(di['mean'],saved_di.mean_speed_kmh) and np.array_equal(di['size'],saved_di.date_count))
check('percentile_band_from_frozen',np.allclose(di.iloc[:,2],saved_di.q10_speed_kmh) and np.allclose(di.iloc[:,3],saved_di.q90_speed_kmh))
check('diurnal_extrema',di['mean'].idxmax()==3 and di['mean'].idxmin()==19 and round(di.loc[3,'mean'],2)==91.10 and round(di.loc[19,'mean'],2)==86.08)
rain=pd.read_csv(F/'rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv')
rain['endpoint']=pd.to_datetime(rain.timestamp_local)
q=q[q.hour.isin(o.index)].copy();q['endpoint']=q.hour+pd.Timedelta(hours=1)
j=q.merge(rain[['node_id','endpoint','precipitation_mm']],on=['node_id','endpoint'],how='left',validate='one_to_one')
check('all_primary_node_hours_have_precipitation',len(j)==22784 and j.precipitation_mm.notna().all())
j['tenths']=(j.precipitation_mm*10).round().astype(int)
paired=j.groupby('hour').agg(speed=('mean','mean'),precip_tenths=('tenths','sum'),nodes=('node_id','size'))
num=paired.precip_tenths;den=paired.nodes
paired['bin']=np.select([num==0,num<=den,num<=5*den],[0,1,2],default=3)
pg=paired.groupby('bin').speed.agg(['size','mean','median'])
saved_pg=pd.read_csv(B2/'hourly/PRECIPITATION_GROUP_SUMMARY.csv')
check('precipitation_bins_recomputed_from_frozen',np.array_equal(pg['size'],[101,125,153,142]) and np.allclose(pg['mean'],saved_pg.mean_speed_kmh) and np.allclose(pg['median'],saved_pg.median_speed_kmh))
bins=pd.read_csv(B2/'coverage/MISSING_DURATION_BINS.csv')
check('Figure3_run_bins',[13249,2415,507,69,54,43,59,51]==bins.episode_count.iloc[:8].tolist() and bins.episode_count.sum()==16447)
report=dict(check_count=len(checks),failed_count=0,checks=checks,diurnal_range_kmh=float(di['mean'].max()-di['mean'].min()),node_clock_speed_range=[float(nc['mean'].min()),float(nc['mean'].max())],node_clock_sd_range=[float(nc['std'].min()),float(nc['std'].max())],node_clock_date_range=[int(nc['size'].min()),int(nc['size'].max())],precipitation_group_means=pg['mean'].tolist())
(BASE/'FIGURE_VALUES_RECHECK.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='checks'},indent=2))
