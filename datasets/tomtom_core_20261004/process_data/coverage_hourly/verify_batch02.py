"""Independent stdlib reconstruction from frozen records and exported CSVs.
No import from build_batch02; no pandas aggregation reused.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
import csv, hashlib, json, math, statistics, sys

ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
FREEZE=ROOT/'outputs/TomTom_Core_Freeze_20261004'
OUT=Path(sys.argv[1]).resolve()
TOL=1e-10
QA=[]
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def qa(name, ok, detail=''):
    QA.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=str(detail)))
def close(name, pairs):
    pairs=list(pairs)
    errors=[]; missing=0
    for a,b in pairs:
        if b is None:
            missing+=int(a!='')
        else:
            try: errors.append(abs(float(a)-b))
            except (ValueError,TypeError): missing+=1
    maximum=max(errors,default=0.)
    qa(name,missing==0 and maximum<=TOL,dict(values=len(pairs),missing_mismatches=missing,max_abs_error=maximum,tolerance=TOL))
def indexed(rows,keys,name):
    d={tuple(r[k] for k in keys):r for r in rows}
    qa(name+':unique_keys',len(d)==len(rows),len(rows))
    return d
def q(x,p):
    x=sorted(x); index=(len(x)-1)*p; lo=math.floor(index); hi=math.ceil(index)
    return x[lo]+(x[hi]-x[lo])*(index-lo)
def fmt(d): return d.strftime('%Y-%m-%d %H:%M:%S')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    config=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    qa('fixed_protocol',config['primary_node_min_observations']==3 and config['overall_min_nodes']==41 and config['calendar_slots']==2304 and config['weather_field']=='precipitation_mm' and not config['traffic_imputation'])
    lock=read(OUT/'INPUT_LOCK.csv')
    qa('inputs_remain_locked',all(digest(Path(r['path']))==r['sha256_before']==r['sha256_after'] for r in lock),len(lock))
    raw=read(FREEZE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv')
    weather=read(FREEZE/'rainfall_hourly_context_2025-12-08_2025-12-31_51nodes.csv')
    nodes=sorted(r['node_id'] for r in read(FREEZE/'tomtom_node_master_51.csv'))
    start=datetime(2025,12,8)
    slots=[fmt(start+timedelta(minutes=15*i)) for i in range(2304)]
    hours=[fmt(start+timedelta(hours=i)) for i in range(576)]
    last=slots[-1]
    keys={(r['node_id'],r['interval_timestamp_local']) for r in raw}
    qa('native_unique_positions',len(keys)==len(raw)==90929)
    by_nh=defaultdict(list)
    for r in raw:
        h=r['interval_timestamp_local'][:13]+':00:00'
        by_nh[(h,r['node_id'])].append(float(r['current_speed_kmh']))
    mem=read(OUT/'hourly/RAW_NODE_HOUR_MEMBERSHIP.csv')
    cols=['node_id','interval_timestamp_local','current_speed_kmh','source_file','source_row_number','batch_uuid','point_uuid','flow_uuid','raw_observed_flag','imputed_flag']
    def record_tuple(r): return tuple(float(r[k]) if k=='current_speed_kmh' else r[k] for k in cols)
    qa('every_raw_membership_provenance',Counter(record_tuple(r) for r in raw)==Counter(record_tuple(r) for r in mem))
    qa('membership_hour_uses_normalized_slot',all(r['hour_start']==r['interval_timestamp_local'][:13]+':00:00' for r in mem))
    intervals=read(OUT/'coverage/INTERVAL_COVERAGE.csv')
    actual_counts={s:sum((n,s) in keys for n in nodes) for s in slots}
    qa('interval_counts',len(intervals)==2304 and all(int(r['observed_nodes'])==actual_counts[r['interval_timestamp_local']] and int(r['missing_nodes'])==51-actual_counts[r['interval_timestamp_local']] for r in intervals))
    close('interval_percentages',[(r['panel_coverage_pct'],100*actual_counts[r['interval_timestamp_local']]/51) for r in intervals])
    daily=read(OUT/'coverage/DAILY_COVERAGE.csv')
    qa('daily_counts',len(daily)==24 and all(int(r['observed_records'])==sum(v for s,v in actual_counts.items() if s[:10]==r['date_local']) and int(r['panel_denominator'])==4896 for r in daily))
    close('daily_coverage_pct',[(r['panel_coverage_pct'],100*int(r['observed_records'])/4896) for r in daily])
    nc=read(OUT/'coverage/NODE_COVERAGE.csv')
    qa('per_node_coverage_counts',len(nc)==51 and all(int(r['observed_slots'])==sum((r['node_id'],s) in keys for s in slots) and int(r['calendar_slots'])==2304 for r in nc))
    close('node_missing_pct',[(r['missing_pct'],100*(2304-int(r['observed_slots']))/2304) for r in nc])
    expected_ep=[]
    for node in nodes:
        run=[]
        for s in slots+['END_SENTINEL']:
            if s!='END_SENTINEL' and (node,s) not in keys: run.append(s)
            elif run:
                expected_ep.append((node,run[0],run[-1],len(run),run[0]==slots[0],run[-1]==last))
                run=[]
    eps=read(OUT/'coverage/MISSING_EPISODES.csv')
    actual_ep=[(r['node_id'],r['start_missing_slot_local'],r['end_missing_slot_local'],int(r['missing_slot_count']),r['touches_window_start']=='True',r['touches_window_end']=='True') for r in eps]
    qa('maximal_missing_runs_exact',actual_ep==expected_ep,dict(episodes=len(eps),slots=sum(x[3] for x in expected_ep)))
    qa('episode_boundary_flags',all((r['window_truncated']=='True')==(r['touches_window_start']=='True' or r['touches_window_end']=='True') for r in eps))
    close('missing_duration',[(r['duration_h'],int(r['missing_slot_count'])/4) for r in eps])
    labels=['15 min','30 min','45-60 min','>1-2 h','>2-3 h','>3-6 h','>6-12 h','>12-24 h','>24 h']
    limits=[1,2,4,8,12,24,48,96,math.inf]
    bin_counts=Counter(); bin_slots=Counter(); bin_labels_ok=True
    for r in eps:
        k=int(r['missing_slot_count']); label=next(a for a,b in zip(labels,limits) if k<=b)
        bin_counts[label]+=1; bin_slots[label]+=k; bin_labels_ok &= label==r['duration_bin']
    bins=read(OUT/'coverage/MISSING_DURATION_BINS.csv')
    qa('missing_duration_bin_reconciliation',bin_labels_ok and len(bins)==9 and all(int(r['episode_count'])==bin_counts[r['duration_bin']] and int(r['missing_slot_count'])==bin_slots[r['duration_bin']] for r in bins))
    nh=read(OUT/'hourly/NODE_HOUR_VALUES.csv')
    nhidx=indexed(nh,['hour_start','node_id'],'node_hour')
    qa('complete_node_hour_grid',set(nhidx)=={(h,n) for h in hours for n in nodes})
    qa('node_hour_counts',all(int(r['observed_count'])==int(r['valid_speed_count'])==len(by_nh[k]) for k,r in nhidx.items()))
    close('node_hour_observed_means',[(r['observed_snapshot_mean_kmh'],statistics.mean(by_nh[k]) if by_nh[k] else None) for k,r in nhidx.items()])
    close('node_hour_sums',[(r['observed_speed_sum_kmh'],sum(by_nh[k]) if by_nh[k] else None) for k,r in nhidx.items()])
    qa('node_hour_primary_status',all(r['primary_status']==('UNOBSERVED' if not by_nh[k] else 'INSUFFICIENT_1_OR_2' if len(by_nh[k])<3 else 'QUALIFIED_3_OR_4') for k,r in nhidx.items()))
    for m in [2,3,4]:
        qa(f'node_hour_qualification_min{m}',all((r[f'qualified_min{m}']=='True')==(len(by_nh[k])>=m) for k,r in nhidx.items()))
        close(f'node_hour_mean_min{m}',[(r[f'speed_mean_min{m}_kmh'],statistics.mean(by_nh[k]) if len(by_nh[k])>=m else None) for k,r in nhidx.items()])
    widx=indexed(weather,['node_id','timestamp_local'],'weather')
    join=read(OUT/'hourly/NODE_HOUR_ENDPOINT_JOIN.csv')
    jidx=indexed(join,['hour_start','node_id'],'endpoint_join')
    qa('endpoint_join_full_grid',set(jidx)==set(nhidx))
    pairs=[]; join_semantics=True; raw_rain=True
    for (h,n),r in jidx.items():
        endpoint=fmt(datetime.fromisoformat(h)+timedelta(hours=1)); wr=widx.get((n,endpoint))
        join_semantics &= r['hour_end']==endpoint and r['endpoint_match_status']==('MATCHED' if wr else 'MISSING_ENDPOINT') and r['rainfall_timestamp_local']==(endpoint if wr else '')
        pairs.append((r['precipitation_mm'],float(wr['precipitation_mm']) if wr else None))
        raw_rain &= r['rain_mm']=='' if wr is None else abs(float(r['rain_mm'])-float(wr['rain_mm']))<=TOL
    qa('endpoint_semantics_no_time_shift',join_semantics)
    qa('rain_separate_field_preserved',raw_rain)
    close('precipitation_original_no_zero_fill',pairs)
    unmatched=read(OUT/'hourly/UNMATCHED_ENDPOINTS.csv')
    qa('unmatched_exact_tail',len(unmatched)==51 and {(r['hour_start'],r['node_id']) for r in unmatched}=={(hours[-1],n) for n in nodes})
    expect={}; oh={}
    for m in [2,3,4]:
        rows=read(OUT/f'hourly/OVERALL_HOURS_MIN{m}.csv')
        oi=indexed(rows,['hour_start'],f'overall_min{m}'); oh[m]={k[0]:v for k,v in oi.items()}
        qa(f'overall_min{m}_full_hours',set(oh[m])==set(hours))
        means=[]; precip=[]; flags=True; lists=True; sums=True; bins_ok=True
        expect[m]={}
        for h in hours:
            ns=[n for n in nodes if len(by_nh[(h,n)])>=m]; good=len(ns)>=41
            mean=statistics.mean(statistics.mean(by_nh[(h,n)]) for n in ns) if good else None
            end=fmt(datetime.fromisoformat(h)+timedelta(hours=1))
            ws=[widx.get((n,end)) for n in ns]; match=sum(r is not None for r in ws)
            ps=sum(round(float(r['precipitation_mm'])*10) for r in ws) if match==len(ns) and ns else None
            p=ps/(10*len(ns)) if good and ps is not None else None
            label=('P=0' if ps==0 else '0<P<=0.1' if ps<=len(ns) else '0.1<P<=0.5' if ps<=5*len(ns) else 'P>0.5') if p is not None else ''
            r=oh[m][h]
            expect[m][h]=dict(nodes=ns,mean=mean,p=p,label=label,sum=ps)
            lists &= r['valid_node_ids']=='|'.join(ns) and int(r['valid_node_count'])==len(ns)
            flags &= (r['retained_traffic_hour']=='True')==good and r['paired_weather_status']==('PAIRED' if good and p is not None else 'UNMATCHED_WEATHER' if good else 'TRAFFIC_NOT_RETAINED')
            sums &= int(r['raw_membership_count'])==sum(len(by_nh[(h,n)]) for n in ns) and int(r['matched_valid_node_count'])==match and int(r['unmatched_valid_node_count'])==len(ns)-match
            bins_ok &= r['precipitation_group']==label and (int(r['precipitation_sum_tenths_mm'])==ps if p is not None else r['precipitation_sum_tenths_mm']=='')
            means.append((r['overall_speed_kmh'],mean)); precip.append((r['precipitation_mean_mm'],p))
        qa(f'overall_min{m}_exact_node_set',lists)
        qa(f'overall_min{m}_support_flags',flags)
        qa(f'overall_min{m}_membership_and_match_counts',sums)
        qa(f'overall_min{m}_exact_precipitation_bins',bins_ok)
        close(f'overall_min{m}_equal_node_speed',means); close(f'overall_min{m}_same_set_precipitation',precip)
    primary={h:e for h,e in expect[3].items() if e['mean'] is not None}
    clocks=defaultdict(list); node_clock=defaultdict(list); balanced=defaultdict(list)
    for h,e in primary.items(): clocks[int(h[11:13])].append(e['mean'])
    for (h,n),x in by_nh.items():
        if len(x)>=3:
            node_clock[(n,str(int(h[11:13])))].append(statistics.mean(x))
            if h in primary: balanced[(n,str(int(h[11:13])))].append(statistics.mean(x))
    dc=read(OUT/'hourly/DIURNAL_PRIMARY.csv')
    qa('diurnal_clock_dates',len(dc)==24 and all(int(r['date_count'])==len(clocks[int(r['clock_hour_local'])]) for r in dc))
    for col,calc in [('mean_speed_kmh',statistics.mean),('q10_speed_kmh',lambda x:q(x,.1)),('q90_speed_kmh',lambda x:q(x,.9))]:
        close('diurnal_'+col,[(r[col],calc(clocks[int(r['clock_hour_local'])])) for r in dc])
    ncv=read(OUT/'hourly/NODE_CLOCK_VARIABILITY.csv')
    qa('node_clock_dates',len(ncv)==1224 and all(int(r['date_count'])==len(node_clock[(r['node_id'],r['clock_hour_local'])]) for r in ncv))
    close('node_clock_sample_sd',[(r['sample_sd_kmh'],statistics.stdev(node_clock[(r['node_id'],r['clock_hour_local'])])) for r in ncv])
    close('node_clock_means',[(r['mean_speed_kmh'],statistics.mean(node_clock[(r['node_id'],r['clock_hour_local'])])) for r in ncv])
    bn=read(OUT/'hourly/BALANCED_NODE_CLOCK_MEANS.csv')
    qa('balanced_dates_same_primary_support',len(bn)==1224 and all(int(r['date_count'])==len(balanced[(r['node_id'],r['clock_hour_local'])]) for r in bn))
    close('balanced_node_clock_means',[(r['mean_speed_kmh'],statistics.mean(balanced[(r['node_id'],r['clock_hour_local'])])) for r in bn])
    bc=read(OUT/'hourly/DIURNAL_BALANCED_COMPARISON.csv')
    close('balanced_curve_fixed51',[(r['balanced_speed_kmh'],statistics.mean(statistics.mean(balanced[(n,r['clock_hour_local'])]) for n in nodes)) for r in bc])
    samples=read(OUT/'hourly/PRECIPITATION_GROUP_HOUR_SAMPLES.csv')
    qa('precipitation_samples_exact',len(samples)==len(primary)==521 and {r['hour_start'] for r in samples}==set(primary))
    groups=read(OUT/'hourly/PRECIPITATION_GROUP_SUMMARY.csv')
    qa('precipitation_four_groups',len(groups)==4)
    stats_checks=defaultdict(list); counts_ok=True
    for r in groups:
        hs=[h for h,e in primary.items() if e['label']==r['precipitation_group']]; x=[primary[h]['mean'] for h in hs]
        counts_ok &= int(r['hour_count'])==len(x) and int(r['date_count'])==len({h[:10] for h in hs}) and int(r['included_node_hours'])==sum(len(primary[h]['nodes']) for h in hs)
        vals=dict(mean_speed_kmh=statistics.mean(x),median_speed_kmh=statistics.median(x),q25_speed_kmh=q(x,.25),q75_speed_kmh=q(x,.75),iqr_speed_kmh=q(x,.75)-q(x,.25),sample_sd_kmh=statistics.stdev(x),min_speed_kmh=min(x),max_speed_kmh=max(x))
        for k,v in vals.items(): stats_checks[k].append((r[k],v))
    qa('precipitation_group_counts_and_dates',counts_ok)
    for k,pairs in stats_checks.items(): close('group_'+k,pairs)
    sens=read(OUT/'hourly/SENSITIVITY_COMMON_HOURS_MIN2_MIN3.csv')
    qa('common_hour_support_exact',len(sens)==521 and {r['hour_start'] for r in sens}==set(primary))
    close('common_min2_min3_difference',[(r['min2_minus_min3_speed_kmh'],expect[2][r['hour_start']]['mean']-primary[r['hour_start']]['mean']) for r in sens])
    qa('common_extra_node_ids',all(r['extra_node_ids_min2']=='|'.join(sorted(set(expect[2][r['hour_start']]['nodes'])-set(primary[r['hour_start']]['nodes']))) for r in sens))
    wd=read(OUT/'hourly/WEIGHT_DEFINITION_DIAGNOSTIC.csv')
    pooled=[]
    for r in wd:
        h=r['hour_start']; x=[v for n in primary[h]['nodes'] for v in by_nh[(h,n)]]
        pooled.append((r['pooled_raw_record_speed_kmh'],statistics.mean(x)))
    close('weight_definition_pooled_original_memberships',pooled)
    close('weight_definition_absolute_difference',[(r['absolute_difference_kmh'],abs(float(r['pooled_raw_record_speed_kmh'])-primary[r['hour_start']]['mean'])) for r in wd])
    dc2=read(OUT/'hourly/DIURNAL_MIN2.csv')
    clocks2=defaultdict(list)
    for h,e in expect[2].items():
        if e['mean'] is not None: clocks2[int(h[11:13])].append(e['mean'])
    qa('min2_diurnal_date_counts',len(dc2)==24 and all(int(r['date_count'])==len(clocks2[int(r['clock_hour_local'])]) for r in dc2))
    close('min2_diurnal_means',[(r['mean_speed_kmh'],statistics.mean(clocks2[int(r['clock_hour_local'])])) for r in dc2])
    for col,p in [('q10_speed_kmh',.1),('q90_speed_kmh',.9)]:
        close('min2_diurnal_'+col,[(r[col],q(clocks2[int(r['clock_hour_local'])],p)) for r in dc2])
    supports=read(OUT/'hourly/SENSITIVITY_SUPPORT_SUMMARY.csv')
    scounts=True; spairs=[]
    for r in supports:
        m=int(r['threshold'])
        g=primary.keys() if r['comparison']=='COMMON_CALENDAR_HOURS' else [h for h,e in expect[m].items() if e['mean'] is not None]
        x=[expect[m][h]['mean'] for h in g]
        scounts &= int(r['hour_count'])==len(x) and int(r['included_node_hours'])==sum(len(expect[m][h]['nodes']) for h in g)
        spairs.append((r['mean_speed_kmh'],statistics.mean(x) if x else None))
    qa('sensitivity_own_and_common_support_counts',scounts and len(supports)==5)
    close('sensitivity_own_and_common_support_means',spairs)
    summary=json.loads((OUT/'RESULT_SUMMARY.json').read_text(encoding='utf-8'))
    qa('summary_scope_counts',summary['coverage']['missing_positions']==sum(x[3] for x in expected_ep)==26575 and summary['hourly']['primary_hours']==len(primary) and summary['hourly']['included_node_hours']==sum(len(e['nodes']) for e in primary.values()))
    close('summary_overall_mean',[(summary['hourly']['overall_retained_mean_kmh'],statistics.mean(e['mean'] for e in primary.values()))])
    build=read(OUT/'qa/BUILD_QA.csv')
    qa('build_checks_all_pass',all(r['status']=='PASS' for r in build),len(build))
    with (OUT/'qa/INDEPENDENT_QA.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['check','status','detail']);writer.writeheader();writer.writerows(QA)
    report=dict(completed_utc=datetime.now(timezone.utc).isoformat(),verifier_sha256=digest(Path(__file__)),python=sys.version,check_count=len(QA),failed_count=sum(r['status']=='FAIL' for r in QA),checks=QA)
    (OUT/'qa/INDEPENDENT_QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(check_count=len(QA),failed=[r for r in QA if r['status']=='FAIL']),ensure_ascii=False,indent=2))
    if report['failed_count']: raise SystemExit(1)

if __name__=='__main__': main()
