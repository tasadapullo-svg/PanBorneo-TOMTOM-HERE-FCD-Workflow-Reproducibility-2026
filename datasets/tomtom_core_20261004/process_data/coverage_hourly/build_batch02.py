"""E04/E05 frozen-input descriptive analysis. No input mutation or imputation.
Run with bundled Python: build_batch02.py --output-dir NEW_DIRECTORY
"""
from pathlib import Path
import argparse, hashlib, json, platform, sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd

ROOT = Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
FREEZE = ROOT / 'outputs/TomTom_Core_Freeze_20261004'
PREP = ROOT / 'outputs/Manuscript_Preparation_20261006'
B01 = ROOT / 'outputs/Manuscript_Execution_20261006_b01_054939Z/batch01_preflight'
ANCHORS = {
    'SHA256_MANIFEST.csv': 'b38f799858a7af711a81e217e66390d733ae53c53bc2367cf01c988271116111',
    'tomtom_15min_frozen_2025-12-08_2025-12-31.csv': '8fb1bd523b560ca4cfe14c1c4eb258cad2c98fffc570d04119f6a4f26048f36d',
    'rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv': '9c85bd5583577030a760caf70952850da31a458654bf9d23ce25dad2e5b6f5c8',
}
BINS = ['15 min', '30 min', '45-60 min', '>1-2 h', '>2-3 h', '>3-6 h', '>6-12 h', '>12-24 h', '>24 h']
P_GROUPS = ['P=0', '0<P<=0.1', '0.1<P<=0.5', 'P>0.5']

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
    return h.hexdigest()

def main(out):
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if (out/'CONFIG.json').exists(): raise RuntimeError('Refusing to overwrite an existing run')
    for d in ['coverage', 'hourly', 'qa']: (out/d).mkdir(exist_ok=True)
    checks = []
    def check(name, actual, expected):
        ok = actual == expected
        checks.append(dict(check=name, actual=str(actual), expected=str(expected), status='PASS' if ok else 'FAIL'))
        if not ok: raise AssertionError(f'{name}: {actual!r} != {expected!r}')
    def csv(df, name):
        df.to_csv(out/name, index=False, encoding='utf-8-sig', float_format='%.17g', na_rep='')
    def dump(obj, name):
        (out/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    config = dict(freeze_id='TOMTOM_CORE_20261004', timezone='Asia/Kuching',
        window_start='2025-12-08 00:00:00', window_last_slot='2025-12-31 23:45:00',
        node_count=51, calendar_slots=2304, calendar_hours=576, expected_slots_per_node_hour=4,
        primary_node_min_observations=3, sensitivity_node_min_observations=[2,4],
        overall_min_nodes=41, node_weight='equal within each qualified hour',
        clock_weight='equal qualified dates within local clock hour',
        node_clock_sd='sample SD ddof=1 over all qualified node hours; >=2 dates',
        balanced_clock='same 521-hour primary support; node-clock means then equal 51 nodes',
        weather_field='precipitation_mm', weather_unit='mm accumulated over preceding hour',
        weather_join='node_id and hour_end = original background timestamp',
        precipitation_bin_rule='assert source 0.1 mm precision; sum integer tenths / same valid node count',
        precipitation_precision_tolerance=1e-8, quantile_method='linear',
        export_missing='empty CSV field; status and count distinguish missingness',
        independent_numeric_tolerance=1e-10, traffic_imputation=False,
        allowed_analysis='E04/E05 descriptive; no models, figures, Word editing or publication')
    dump(config, 'CONFIG.json')
    lock = []
    mf = pd.read_csv(FREEZE/'SHA256_MANIFEST.csv')
    expected = dict(zip(mf.file, mf.sha256)) | ANCHORS
    for name, exp in expected.items():
        p = FREEZE/name
        actual = sha(p)
        check('input_hash:'+name, actual, exp)
        lock.append(dict(path=str(p), bytes=p.stat().st_size, expected_sha256=exp, sha256_before=actual))
    for p in [PREP/'论文写作交接与结果证据清单.md', B01/'BATCH01_ACCEPTANCE.md', B01/'SEMANTICS_AUDIT.md']:
        lock.append(dict(path=str(p), bytes=p.stat().st_size, expected_sha256='', sha256_before=sha(p)))

    t = pd.read_csv(FREEZE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv')
    w = pd.read_csv(FREEZE/'rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv')
    master = pd.read_csv(FREEZE/'tomtom_node_master_51.csv')
    slots = pd.date_range(config['window_start'], config['window_last_slot'], freq='15min')
    hours = pd.date_range(config['window_start'], '2025-12-31 23:00:00', freq='h')
    nodes = sorted(master.node_id.tolist())
    check('traffic_rows', len(t), 90929)
    check('master_unique_nodes', len(set(nodes)), 51)
    t['slot'] = pd.to_datetime(t.interval_timestamp_local)
    t['hour_start'] = t.slot.dt.floor('h')
    check('traffic_key_duplicates', int(t.duplicated(['node_id','slot']).sum()), 0)
    check('traffic_keys_in_grid', bool(t.node_id.isin(nodes).all() and t.slot.isin(slots).all()), True)
    check('traffic_flags', bool((t.raw_observed_flag=='YES').all() and (t.imputed_flag=='NO').all()), True)
    check('traffic_timezone', set(t.timezone), {'Asia/Kuching'})
    check('valid_speed_rows', int((np.isfinite(t.current_speed_kmh) & (t.current_speed_kmh>=0)).sum()), len(t))
    w['rainfall_timestamp_local'] = pd.to_datetime(w.timestamp_local)
    check('weather_rows', len(w), 29376)
    check('weather_key_duplicates', int(w.duplicated(['node_id','rainfall_timestamp_local']).sum()), 0)
    check('weather_keys_full_grid', bool(w.node_id.isin(nodes).all() and w.rainfall_timestamp_local.isin(hours).all()), True)
    check('weather_nonnegative_finite', bool((np.isfinite(w.precipitation_mm) & (w.precipitation_mm>=0)).all()), True)
    precision_error = float(np.abs(w.precipitation_mm*10-np.rint(w.precipitation_mm*10)).max())
    check('weather_source_tenth_mm_precision', precision_error < config['precipitation_precision_tolerance'], True)
    w['precipitation_tenths_mm'] = pd.array(np.rint(w.precipitation_mm*10), dtype='Int64')
    mapping = w[['node_id','node_order_verified','weather_grid_id']].drop_duplicates()
    check('stable_node_mapping', len(mapping), 51)
    check('source_node_order_permutation', sorted(mapping.node_order_verified.tolist()), list(range(1,52)))
    check('grid_count', mapping.weather_grid_id.nunique(), 15)
    check('within_grid_precipitation_consistency', int((w.groupby(['weather_grid_id','rainfall_timestamp_local']).precipitation_mm.nunique()>1).sum()), 0)
    csv(mapping.sort_values('node_order_verified'), 'hourly/NODE_DISPLAY_MAPPING.csv')

    # E04: full native observation grid, never first/last observed-span denominator.
    present = np.zeros((len(slots),len(nodes)), dtype=bool)
    ni = {n:i for i,n in enumerate(nodes)}
    present[slots.get_indexer(t.slot), t.node_id.map(ni).to_numpy()] = True
    counts = present.sum(axis=1)
    interval = pd.DataFrame(dict(interval_timestamp_local=slots, observed_nodes=counts,
        missing_nodes=51-counts, panel_denominator=51, panel_coverage_pct=counts/51*100,
        typical_batch_reference_denominator=42, typical_batch_reference_pct=counts/42*100))
    interval['empty_slot_class'] = np.where(counts>0, 'OBSERVED', np.where(slots<t.slot.min(), 'PRE_FIRST_OBSERVATION', np.where(slots>t.slot.max(),'POST_LAST_OBSERVATION','INTERNAL_EMPTY')))
    csv(interval, 'coverage/INTERVAL_COVERAGE.csv')
    freeze_interval = pd.read_csv(FREEZE/'tomtom_interval_coverage_2304.csv')
    check('freeze_interval_count_agreement', bool(np.array_equal(counts, freeze_interval.observed_records)), True)
    daily = interval.assign(date_local=interval.interval_timestamp_local.dt.strftime('%Y-%m-%d')).groupby('date_local').agg(observed_records=('observed_nodes','sum'), observed_slots=('observed_nodes',lambda x:int((x>0).sum()))).reset_index()
    daily['calendar_slots']=96; daily['panel_denominator']=51*96
    daily['missing_positions']=daily.panel_denominator-daily.observed_records
    daily['panel_coverage_pct']=100*daily.observed_records/daily.panel_denominator
    daily['slot_presence_pct']=100*daily.observed_slots/96
    daily['typical_batch_reference_denominator']=42*96
    daily['typical_batch_reference_pct']=100*daily.observed_records/(42*96)
    csv(daily, 'coverage/DAILY_COVERAGE.csv')
    nc = pd.DataFrame(dict(node_id=nodes, observed_slots=present.sum(axis=0), calendar_slots=len(slots)))
    nc['missing_slots']=nc.calendar_slots-nc.observed_slots
    nc['coverage_pct']=100*nc.observed_slots/nc.calendar_slots
    nc['missing_pct']=100*nc.missing_slots/nc.calendar_slots
    nc=nc.merge(mapping, on='node_id',validate='one_to_one')
    csv(nc.sort_values('node_order_verified'), 'coverage/NODE_COVERAGE.csv')
    check('freeze_node_count_agreement', bool((nc.set_index('node_id').observed_slots.sort_index()==master.set_index('node_id').record_count.sort_index()).all()), True)
    episodes=[]
    for j,node in enumerate(nodes):
        missing = ~present[:,j]
        edges = np.diff(np.r_[False,missing,False].astype(int))
        starts=np.flatnonzero(edges==1); ends=np.flatnonzero(edges==-1)-1
        for start,end in zip(starts,ends):
            k=int(end-start+1)
            b = BINS[0] if k==1 else BINS[1] if k==2 else BINS[2] if k<=4 else BINS[3] if k<=8 else BINS[4] if k<=12 else BINS[5] if k<=24 else BINS[6] if k<=48 else BINS[7] if k<=96 else BINS[8]
            episodes.append(dict(episode_id=f'E{len(episodes)+1:05d}', node_id=node, start_missing_slot_local=slots[start], end_missing_slot_local=slots[end], missing_slot_count=k, duration_h=k*.25, touches_window_start=bool(start==0), touches_window_end=bool(end==len(slots)-1), window_truncated=bool(start==0 or end==len(slots)-1), duration_bin=b))
    ep=pd.DataFrame(episodes)
    csv(ep,'coverage/MISSING_EPISODES.csv')
    bins=ep.groupby('duration_bin').agg(episode_count=('episode_id','size'),missing_slot_count=('missing_slot_count','sum')).reindex(BINS,fill_value=0).reset_index()
    csv(bins,'coverage/MISSING_DURATION_BINS.csv')
    check('missing_positions', int((~present).sum()), 26575)
    check('episode_count',len(ep),16447)
    check('episode_slot_sum',int(ep.missing_slot_count.sum()),26575)
    check('episode_boundary_count',int(ep.window_truncated.sum()),60)
    check('episode_internal_count',int((~ep.window_truncated).sum()),16387)
    check('missing_bin_counts',bins.episode_count.tolist(),[13249,2415,507,69,54,43,59,51,0])
    check('all_empty_slots',int((counts==0).sum()),138)
    check('pre_first_empty_slots',int((interval.empty_slot_class=='PRE_FIRST_OBSERVATION').sum()),53)
    check('internal_empty_slots',int((interval.empty_slot_class=='INTERNAL_EMPTY').sum()),85)

    # E05: all actual memberships + full grid node hours with distinct status codes.
    mem=t[['node_id','hour_start','interval_timestamp_local','current_speed_kmh','source_file','source_row_number','batch_uuid','point_uuid','flow_uuid','raw_observed_flag','imputed_flag']].sort_values(['hour_start','node_id','interval_timestamp_local'])
    csv(mem,'hourly/RAW_NODE_HOUR_MEMBERSHIP.csv')
    nh=t.groupby(['hour_start','node_id']).agg(observed_count=('slot','size'),valid_speed_count=('current_speed_kmh','count'), observed_speed_sum_kmh=('current_speed_kmh','sum'),observed_snapshot_mean_kmh=('current_speed_kmh','mean'))
    nh=nh.reindex(pd.MultiIndex.from_product([hours,nodes],names=['hour_start','node_id'])).reset_index()
    nh[['observed_count','valid_speed_count']]=nh[['observed_count','valid_speed_count']].fillna(0).astype(int)
    nh['hour_end']=nh.hour_start+pd.Timedelta(hours=1)
    nh['date_local']=nh.hour_start.dt.strftime('%Y-%m-%d'); nh['clock_hour_local']=nh.hour_start.dt.hour
    nh['primary_status']=np.select([nh.observed_count==0,nh.valid_speed_count<3],['UNOBSERVED','INSUFFICIENT_1_OR_2'],'QUALIFIED_3_OR_4')
    for threshold in [2,3,4]:
        nh[f'qualified_min{threshold}']=nh.valid_speed_count>=threshold
        nh[f'speed_mean_min{threshold}_kmh']=nh.observed_snapshot_mean_kmh.where(nh[f'qualified_min{threshold}'])
    nh=nh.merge(mapping,on='node_id',validate='many_to_one')
    csv(nh,'hourly/NODE_HOUR_VALUES.csv')
    nhdist=nh.observed_count.value_counts().reindex(range(5),fill_value=0)
    check('node_hour_observation_distribution',nhdist.tolist(),[1543,663,3650,11114,12406])
    csv(nhdist.rename_axis('observed_count').rename('node_hour_count').reset_index(),'hourly/NODE_HOUR_SUPPORT_COUNTS.csv')
    bg=w[['node_id','rainfall_timestamp_local','precipitation_mm','rain_mm','precipitation_tenths_mm','timestamp_utc','source_model','download_timestamp']].rename(columns={'timestamp_utc':'rainfall_timestamp_utc'})
    join=nh.merge(bg,left_on=['node_id','hour_end'],right_on=['node_id','rainfall_timestamp_local'],how='left',validate='one_to_one',indicator=True)
    join['endpoint_match_status']=np.where(join['_merge']=='both','MATCHED','MISSING_ENDPOINT')
    join=join.drop(columns='_merge')
    csv(join,'hourly/NODE_HOUR_ENDPOINT_JOIN.csv')
    csv(join[join.endpoint_match_status!='MATCHED'],'hourly/UNMATCHED_ENDPOINTS.csv')
    check('full_grid_unmatched_node_hours',int((join.endpoint_match_status!='MATCHED').sum()),51)
    results={}
    for threshold in [2,3,4]:
        rows=[]
        for h, full in join.groupby('hour_start',sort=True):
            g=full[full[f'qualified_min{threshold}']].sort_values('node_id')
            n=len(g); retained=n>=41
            match=bool(n>0 and g.precipitation_mm.notna().all())
            p_sum=int(g.precipitation_tenths_mm.sum()) if match else None
            pmean=p_sum/(10*n) if match and retained else None
            group = ('P=0' if p_sum==0 else '0<P<=0.1' if p_sum<=n else '0.1<P<=0.5' if p_sum<=5*n else 'P>0.5') if pmean is not None else ''
            rows.append(dict(hour_start=h,hour_end=h+pd.Timedelta(hours=1),date_local=h.strftime('%Y-%m-%d'),clock_hour_local=h.hour,threshold=threshold,valid_node_count=n,valid_node_ids='|'.join(g.node_id), retained_traffic_hour=retained,traffic_status='RETAINED' if retained else 'BELOW_41_NODES', overall_speed_kmh=float(g.observed_snapshot_mean_kmh.mean()) if retained else None,raw_membership_count=int(g.observed_count.sum()),matched_valid_node_count=int(g.precipitation_mm.notna().sum()),unmatched_valid_node_count=int(g.precipitation_mm.isna().sum()),paired_weather_status='PAIRED' if retained and match else 'UNMATCHED_WEATHER' if retained else 'TRAFFIC_NOT_RETAINED',precipitation_sum_tenths_mm=p_sum if retained and match else None, precipitation_mean_mm=pmean, precipitation_group=group))
        oh=pd.DataFrame(rows)
        oh['precipitation_sum_tenths_mm']=pd.array(oh.precipitation_sum_tenths_mm,dtype='Int64')
        csv(oh,f'hourly/OVERALL_HOURS_MIN{threshold}.csv')
        results[threshold]=oh
        check(f'qualified_node_hours_min{threshold}',int(nh[f'qualified_min{threshold}'].sum()),{2:27170,3:23520,4:12406}[threshold])
        check(f'retained_overall_hours_min{threshold}',int(oh.retained_traffic_hour.sum()),{2:542,3:521,4:0}[threshold])
    primary=results[3][results[3].retained_traffic_hour].copy()
    check('primary_included_node_hours',int(primary.valid_node_count.sum()),22784)
    check('primary_all_weather_matched',set(primary.paired_weather_status),{'PAIRED'})
    check('primary_node_count_range',[int(primary.valid_node_count.min()),int(primary.valid_node_count.max())],[41,48])
    def clock_stats(frame):
        return frame.groupby('clock_hour_local').overall_speed_kmh.agg(date_count='size',mean_speed_kmh='mean',q10_speed_kmh=lambda x:x.quantile(.1,interpolation='linear'),q90_speed_kmh=lambda x:x.quantile(.9,interpolation='linear')).reindex(range(24)).reset_index()
    diurnal=clock_stats(primary)
    csv(diurnal,'hourly/DIURNAL_PRIMARY.csv')
    csv(clock_stats(results[2][results[2].retained_traffic_hour]),'hourly/DIURNAL_MIN2.csv')
    qualified=nh[nh.qualified_min3].copy()
    ncstats=qualified.groupby(['node_id','clock_hour_local']).observed_snapshot_mean_kmh.agg(date_count='size',mean_speed_kmh='mean',sample_sd_kmh='std').reset_index().merge(mapping,on='node_id',validate='many_to_one')
    ncstats.loc[ncstats.date_count<2,'sample_sd_kmh']=np.nan
    csv(ncstats.sort_values(['node_order_verified','clock_hour_local']),'hourly/NODE_CLOCK_VARIABILITY.csv')
    common_nh=qualified[qualified.hour_start.isin(primary.hour_start)]
    balanced=common_nh.groupby(['node_id','clock_hour_local']).observed_snapshot_mean_kmh.agg(date_count='size',mean_speed_kmh='mean').reset_index().merge(mapping,on='node_id',validate='many_to_one')
    check('balanced_node_clock_groups',len(balanced),1224)
    csv(balanced.sort_values(['node_order_verified','clock_hour_local']),'hourly/BALANCED_NODE_CLOCK_MEANS.csv')
    bc=balanced.groupby('clock_hour_local').agg(node_count=('node_id','size'),balanced_speed_kmh=('mean_speed_kmh','mean'),min_dates_per_node=('date_count','min'),max_dates_per_node=('date_count','max')).reset_index().merge(diurnal[['clock_hour_local','mean_speed_kmh']],on='clock_hour_local',validate='one_to_one')
    bc['balanced_minus_primary_kmh']=bc.balanced_speed_kmh-bc.mean_speed_kmh
    check('balanced_51_nodes_every_clock',bool((bc.node_count==51).all()),True)
    csv(bc,'hourly/DIURNAL_BALANCED_COMPARISON.csv')
    csv(primary,'hourly/PRECIPITATION_GROUP_HOUR_SAMPLES.csv')
    gs=[]
    for label in P_GROUPS:
        g=primary[primary.precipitation_group==label]; x=g.overall_speed_kmh
        gs.append(dict(precipitation_group=label,hour_count=len(g),date_count=g.date_local.nunique(),included_node_hours=int(g.valid_node_count.sum()),min_nodes=int(g.valid_node_count.min()),max_nodes=int(g.valid_node_count.max()),mean_speed_kmh=float(x.mean()),median_speed_kmh=float(x.median()),q25_speed_kmh=float(x.quantile(.25)),q75_speed_kmh=float(x.quantile(.75)),iqr_speed_kmh=float(x.quantile(.75)-x.quantile(.25)),sample_sd_kmh=float(x.std(ddof=1)),min_speed_kmh=float(x.min()),max_speed_kmh=float(x.max())))
    groups=pd.DataFrame(gs)
    csv(groups,'hourly/PRECIPITATION_GROUP_SUMMARY.csv')
    check('precipitation_group_hours',groups.hour_count.tolist(),[101,125,153,142])
    check('precipitation_group_dates',groups.date_count.tolist(),[22,22,23,22])
    # Compare sensitivity on each retained support and on identical calendar hours.
    common=results[2][results[2].retained_traffic_hour].merge(primary,on='hour_start',suffixes=('_min2','_min3'),validate='one_to_one')
    common['min2_minus_min3_speed_kmh']=common.overall_speed_kmh_min2-common.overall_speed_kmh_min3
    common['extra_nodes_min2']=common.valid_node_count_min2-common.valid_node_count_min3
    common['node_set_changed']=common.valid_node_ids_min2!=common.valid_node_ids_min3
    common['extra_node_ids_min2']=[ '|'.join(sorted(set(a.split('|'))-set(b.split('|')))) for a,b in zip(common.valid_node_ids_min2,common.valid_node_ids_min3)]
    csv(common,'hourly/SENSITIVITY_COMMON_HOURS_MIN2_MIN3.csv')
    srows=[]
    for threshold in [2,3,4]:
        g=results[threshold][results[threshold].retained_traffic_hour]
        srows.append(dict(comparison='OWN_RETAINED_SUPPORT',threshold=threshold,hour_count=len(g),included_node_hours=int(g.valid_node_count.sum()),mean_speed_kmh=float(g.overall_speed_kmh.mean()) if len(g) else None))
    for threshold in [2,3]:
        srows.append(dict(comparison='COMMON_CALENDAR_HOURS',threshold=threshold,hour_count=len(common),included_node_hours=int(common[f'valid_node_count_min{threshold}'].sum()),mean_speed_kmh=float(common[f'overall_speed_kmh_min{threshold}'].mean())))
    csv(pd.DataFrame(srows),'hourly/SENSITIVITY_SUPPORT_SUMMARY.csv')
    pooled=common_nh.groupby('hour_start').agg(speed_sum=('observed_speed_sum_kmh','sum'),raw_count=('observed_count','sum')).reset_index()
    pooled=pooled.merge(primary[['hour_start','overall_speed_kmh']],on='hour_start',validate='one_to_one')
    pooled['pooled_raw_record_speed_kmh']=pooled.speed_sum/pooled.raw_count
    pooled['pooled_minus_node_equal_kmh']=pooled.pooled_raw_record_speed_kmh-pooled.overall_speed_kmh
    pooled['absolute_difference_kmh']=pooled.pooled_minus_node_equal_kmh.abs()
    csv(pooled,'hourly/WEIGHT_DEFINITION_DIAGNOSTIC.csv')
    summary=dict(coverage=dict(observed_positions=len(t),panel_denominator=117504,missing_positions=26575,coverage_pct=len(t)/117504*100,missing_pct=26575/117504*100,reference42_pct=len(t)/96768*100,observed_slots=int((counts>0).sum()),slot_presence_pct=float((counts>0).mean()*100),empty_slots=138,pre_first_empty_slots=53,internal_empty_slots=85,episode_count=len(ep),boundary_episodes=int(ep.window_truncated.sum()),internal_episodes=int((~ep.window_truncated).sum()),median_duration_h=float(ep.duration_h.median()),max_duration_h=float(ep.duration_h.max()),max_internal_duration_h=float(ep.loc[~ep.window_truncated,'duration_h'].max()),node_missing_pct_min=float(nc.missing_pct.min()),node_missing_pct_max=float(nc.missing_pct.max())),
        hourly=dict(qualified_node_hours=int(nh.qualified_min3.sum()),primary_hours=len(primary),excluded_hours=576-len(primary),included_node_hours=int(primary.valid_node_count.sum()),min_nodes=int(primary.valid_node_count.min()),max_nodes=int(primary.valid_node_count.max()),all_grid_unmatched_endpoints=51,primary_unmatched_endpoints=int(primary.unmatched_valid_node_count.sum()),primary_zero_precipitation_hours=int((primary.precipitation_group=='P=0').sum()),clock_dates_min=int(diurnal.date_count.min()),clock_dates_max=int(diurnal.date_count.max()),node_clock_dates_min=int(ncstats.date_count.min()),node_clock_dates_max=int(ncstats.date_count.max()),balanced_node_clock_dates_min=int(balanced.date_count.min()),balanced_node_clock_dates_max=int(balanced.date_count.max()),overall_retained_mean_kmh=float(primary.overall_speed_kmh.mean()),lowest_clock=int(diurnal.loc[diurnal.mean_speed_kmh.idxmin(),'clock_hour_local']),highest_clock=int(diurnal.loc[diurnal.mean_speed_kmh.idxmax(),'clock_hour_local']),groups=gs),
        sensitivity=dict(common_hours=len(common),changed_node_set_hours=int(common.node_set_changed.sum()),mean_signed_min2_minus_min3_kmh=float(common.min2_minus_min3_speed_kmh.mean()),median_absolute_min2_minus_min3_kmh=float(common.min2_minus_min3_speed_kmh.abs().median()),max_absolute_min2_minus_min3_kmh=float(common.min2_minus_min3_speed_kmh.abs().max()),balanced_primary_max_abs_kmh=float(bc.balanced_minus_primary_kmh.abs().max()),pooled_equal_median_abs_kmh=float(pooled.absolute_difference_kmh.median()),pooled_equal_max_abs_kmh=float(pooled.absolute_difference_kmh.max())),
        precision_max_error=precision_error)
    for r in lock:
        r['sha256_after']=sha(Path(r['path']))
        check('input_unchanged:'+Path(r['path']).name,r['sha256_after'],r['sha256_before'])
    csv(pd.DataFrame(lock),'INPUT_LOCK.csv')
    csv(pd.DataFrame(checks),'qa/BUILD_QA.csv')
    dump(summary,'RESULT_SUMMARY.json')
    dump(dict(startup_config='CONFIG.json',completed_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,executable=sys.executable,pandas=pd.__version__,numpy=np.__version__,platform=platform.platform(),script_sha256=sha(Path(__file__)),output_dir=str(out)), 'RUN_CONTEXT.json')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print(f'BUILD_QA: {len(checks)} PASS; outputs={out}')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path,required=True)
    main(parser.parse_args().output_dir)
