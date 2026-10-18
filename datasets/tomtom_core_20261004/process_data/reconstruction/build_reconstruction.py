"""Confirmed E06 retrospective single-node gap benchmark, frozen raw speeds only.
Use --output-dir NEW_DIRECTORY. No input writes, interpolation before masking,
hyperparameter selection, confidence intervals, or forecasting.
"""
from pathlib import Path
from collections import defaultdict, deque, Counter
from datetime import datetime, timedelta, timezone
import argparse, hashlib, json, math, platform, sys
import numpy as np
import pandas as pd

ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
FREEZE=ROOT/'outputs/TomTom_Core_Freeze_20261004'
HANDOFF=ROOT/'outputs/Manuscript_Preparation_20261006/论文写作交接与结果证据清单.md'
B02=ROOT/'outputs/Manuscript_Execution_20261006_b02_060919Z/batch02_coverage_hourly'
METHODS=['Linear','LOCF','Train-TOD median','Spatial median']
KS=[1,4,12,24]
SEED=20261006
START=datetime(2025,12,28)
END=datetime(2026,1,1)
DELTA=timedelta(minutes=15)
FAIL_ORDER=['OUTSIDE_TEST_CONTEXT','TARGET_NATURAL_MISSING','ENDPOINT_MISSING','TRAIN_TOD_SUPPORT_LT3','OTHER_NODE_SUPPORT_LT3']

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def fmt(d):return d.strftime('%Y-%m-%d %H:%M:%S')
def tod(d):return d.hour*4+d.minute//15
def write_csv(p,rows,columns=None):
    df=rows if isinstance(rows,pd.DataFrame) else pd.DataFrame(rows,columns=columns)
    df.to_csv(p,index=False,encoding='utf-8-sig',float_format='%.17g',na_rep='')
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def reconstruct(view):
    """Only allowed masked inputs; scorer/hidden targets are never accepted."""
    assert set(view)=={'K','left_speed','right_speed','train_tod','other_speeds'}
    k=view['K'];left=view['left_speed'];right=view['right_speed']
    return {
        'Linear':[left+(j+1)/(k+1)*(right-left) for j in range(k)],
        'LOCF':[left]*k,
        'Train-TOD median':[r['median'] for r in view['train_tod']],
        'Spatial median':[float(np.median(v)) for v in view['other_speeds']],
    }

def main(out):
    out=out.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'CONFIG.json').exists():raise RuntimeError('Refusing to overwrite a run')
    for d in ['inputs','reference','results','qa']:(out/d).mkdir(exist_ok=True)
    qa=[]
    def check(name,actual,expected):
        ok=actual==expected;qa.append(dict(check=name,actual=str(actual),expected=str(expected),status='PASS' if ok else 'FAIL'))
        if not ok:raise AssertionError(f'{name}: {actual!r} != {expected!r}')
    config=dict(freeze_id='TOMTOM_CORE_20261004',timezone='Asia/Kuching',step_minutes=15,
        train=['2025-12-08 00:00:00','2025-12-24 00:00:00'],validation=['2025-12-24 00:00:00','2025-12-28 00:00:00'],test=[fmt(START),fmt(END)],partitions='left-closed right-open normalized slot membership',
        lengths_K=KS,maximum_selected_gaps_per_length=300,seed=SEED,generator='PCG64',substreams='SeedSequence(20261006).spawn(4), ordered K=1,4,12,24',
        train_tod_min_observations=3,other_node_min_observations=3,
        candidate_universe='each of 51 nodes x each of 384 test start slots; boundary gate first',
        eligibility_order=FAIL_ORDER,selection_order='sort(node_id,start_date,t0); shuffle candidates within each sorted group; shuffle group order; round-robin; skip any closed-context overlap on same node across dates',
        overlap_rule='closed [left_endpoint,right_endpoint] windows may not share even an endpoint within same K/node',
        nonoverlap_capacity='maximum cardinality per node by earliest-ending eligible context; reported separately from seeded maximal/capped sampler',
        experiments='each gap starts independently from frozen base; only one node-gap masked; other-node original records visible',
        methods={'Linear':'left + j/(K+1)*(right-left), j=1..K; future right endpoint permitted retrospectively','LOCF':'left endpoint repeated; no recursive filled values','Train-TOD median':'node and quarter-hour TOD median from training partition only','Spatial median':'median of contemporaneous original speeds of all other available nodes; target node excluded; no topology weighting'},
        model_inputs='K; left/right raw speed; frozen train-TOD values; other-node raw speeds. Hidden target scores separate; no ancillary traffic fields.',
        speed_unit='km/h',error_sign='reconstruction minus hidden provider observation',
        primary_RMSE='sqrt(sum(point_error**2)/(N*K)) within length and method',MAE='sum(abs(point_error))/(N*K)',
        gap_distribution='per-gap RMSE median,Q25,Q75 linear empirical quantiles; not CI',
        validation_use='reserved; no tuning performed',prediction_clipping=False,fallback=False,traffic_imputation_of_natural_gaps=False,
        failure_handling='retain failed prediction records; compare only complete gaps common to all methods; report each planned/complete/common/failed count',
        bootstrap=False,forecasting=False,numeric_QA_tolerance=1e-10)
    dump(out/'CONFIG.json',config)
    lock=[]
    mf=pd.read_csv(FREEZE/'SHA256_MANIFEST.csv')
    expected=dict(zip(mf.file,mf.sha256))
    expected['SHA256_MANIFEST.csv']='b38f799858a7af711a81e217e66390d733ae53c53bc2367cf01c988271116111'
    expected['tomtom_15min_frozen_2025-12-08_2025-12-31.csv']='8fb1bd523b560ca4cfe14c1c4eb258cad2c98fffc570d04119f6a4f26048f36d'
    for name,exp in expected.items():
        p=FREEZE/name;a=sha(p);check('input_hash:'+name,a,exp)
        lock.append(dict(path=str(p),bytes=p.stat().st_size,expected_sha256=exp,sha256_before=a))
    for p in [HANDOFF,B02/'BATCH02_ACCEPTANCE.md',B02/'MANIFEST_VERIFY.json']:
        lock.append(dict(path=str(p),bytes=p.stat().st_size,expected_sha256='',sha256_before=sha(p)))
    t=pd.read_csv(FREEZE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv')
    t['slot']=pd.to_datetime(t.interval_timestamp_local)
    nodes=sorted(pd.read_csv(FREEZE/'tomtom_node_master_51.csv').node_id)
    check('raw_rows',len(t),90929);check('node_count',len(nodes),51)
    check('unique_raw_keys',int(t.duplicated(['node_id','slot']).sum()),0)
    check('nonimputed_raw_flags',bool((t.raw_observed_flag=='YES').all() and (t.imputed_flag=='NO').all()),True)
    check('finite_nonnegative_speed',bool((np.isfinite(t.current_speed_kmh)&(t.current_speed_kmh>=0)).all()),True)
    check('quarter_hour_slots',bool(((t.slot.dt.minute%15==0)&(t.slot.dt.second==0)).all()),True)
    train=t[(t.slot>=pd.Timestamp(config['train'][0]))&(t.slot<pd.Timestamp(config['train'][1]))].copy()
    valid=t[(t.slot>=pd.Timestamp(config['validation'][0]))&(t.slot<pd.Timestamp(config['validation'][1]))]
    test=t[(t.slot>=START)&(t.slot<END)]
    check('partition_rows',[len(train),len(valid),len(test)],[59009,16128,15792])
    write_csv(out/'inputs/PARTITION_COUNTS.csv',[dict(partition=n,raw_rows=len(x),unique_nodes=x.node_id.nunique(),first_observed_slot=fmt(x.slot.min()),last_observed_slot=fmt(x.slot.max()),use=u) for n,x,u in [('train',train,'fit TOD medians only'),('validation',valid,'reserved; no tuning'),('test',test,'candidate support, allowed masked context and scoring reference')]])
    train['tod_quarter_index']=train.slot.dt.hour*4+train.slot.dt.minute//15
    train['tod_local']=train.slot.dt.strftime('%H:%M')
    write_csv(out/'inputs/TRAIN_TOD_MEMBERSHIP.csv',train[['node_id','interval_timestamp_local','tod_quarter_index','tod_local','current_speed_kmh','source_file','source_row_number']].sort_values(['node_id','tod_quarter_index','interval_timestamp_local']))
    ts=train.groupby(['node_id','tod_quarter_index']).current_speed_kmh.agg(observation_count='size',median_speed_kmh='median')
    ts=ts.reindex(pd.MultiIndex.from_product([nodes,range(96)],names=['node_id','tod_quarter_index'])).reset_index()
    ts['observation_count']=ts.observation_count.fillna(0).astype(int)
    ts['reference_qualified']=ts.observation_count>=3
    ts['tod_local']=[f'{i//4:02d}:{(i%4)*15:02d}' for i in ts.tod_quarter_index]
    write_csv(out/'inputs/TRAIN_TOD_STATS.csv',ts)
    stats={(r.node_id,int(r.tod_quarter_index)):dict(count=int(r.observation_count),median=float(r.median_speed_kmh) if pd.notna(r.median_speed_kmh) else None) for r in ts.itertuples()}
    # Training statistics are saved/frozen before inspecting test candidates or scores.
    train_stats_hash=sha(out/'inputs/TRAIN_TOD_STATS.csv')
    raw={(r.node_id,r.slot.to_pydatetime()):dict(speed=float(r.current_speed_kmh),source_file=r.source_file,source_row_number=int(r.source_row_number)) for r in t.itertuples()}
    at=defaultdict(dict)
    for (n,d),r in raw.items():at[d][n]=r
    catalog=[];eligible_by_k={};capacity=[];capacity_keys=[]
    for k in KS:
        eligible=[]
        for n in nodes:
            for i in range(384):
                d=START+i*DELTA;left=d-DELTA;right=d+k*DELTA;targets=[d+j*DELTA for j in range(k)]
                cid=f'K{k:02d}:{n}:{d.strftime("%Y%m%dT%H%M")}'
                row=dict(candidate_id=cid,node_id=n,K=k,duration_h=k/4,t0=fmt(d),last_hidden=fmt(targets[-1]),left_endpoint=fmt(left),right_endpoint=fmt(right),start_date=d.strftime('%Y-%m-%d'),boundary_pass=left>=START and right<END,target_missing_count=None,left_observed=None,right_observed=None,min_train_tod_count=None,min_other_node_count=None)
                fails=[]
                if not row['boundary_pass']:fails.append(FAIL_ORDER[0])
                else:
                    missing=sum((n,x) not in raw for x in targets)
                    lp=(n,left) in raw;rp=(n,right) in raw
                    tr=min(stats[(n,tod(x))]['count'] for x in targets)
                    other=min(len(at[x])-int(n in at[x]) for x in targets)
                    row.update(target_missing_count=missing,left_observed=lp,right_observed=rp,min_train_tod_count=tr,min_other_node_count=other)
                    if missing:fails.append(FAIL_ORDER[1])
                    if not(lp and rp):fails.append(FAIL_ORDER[2])
                    if tr<3:fails.append(FAIL_ORDER[3])
                    if other<3:fails.append(FAIL_ORDER[4])
                row.update(eligible=not fails,first_exclusion_reason=fails[0] if fails else '',all_exclusion_reasons='|'.join(fails),selection_status='INELIGIBLE' if fails else 'NOT_VISITED',sampler_attempt_order=None,sampler_group_rank=None,within_group_shuffle_rank=None)
                catalog.append(row)
                if not fails:eligible.append(row)
        eligible_by_k[k]=eligible
        for n in nodes:
            es=sorted((r for r in eligible if r['node_id']==n),key=lambda r:(r['right_endpoint'],r['left_endpoint']))
            count=0;last_right=None
            for r in es:
                if last_right is None or r['left_endpoint']>last_right:
                    count+=1;last_right=r['right_endpoint'];capacity_keys.append(dict(K=k,node_id=n,candidate_id=r['candidate_id'],left_endpoint=r['left_endpoint'],right_endpoint=r['right_endpoint']))
            capacity.append(dict(K=k,node_id=n,eligible_candidates=len(es),maximum_nonoverlap_contexts=count))
    write_csv(out/'inputs/NONOVERLAP_CAPACITY_BY_NODE.csv',capacity)
    write_csv(out/'inputs/NONOVERLAP_CAPACITY_WITNESS.csv',capacity_keys,['K','node_id','candidate_id','left_endpoint','right_endpoint'])
    # Fixed seeded balanced sampler; no target speed or error enters selection.
    children=np.random.SeedSequence(SEED).spawn(len(KS));rng_records=[];selected=[];selection_counts={}
    for k,child in zip(KS,children):
        rng=np.random.Generator(np.random.PCG64(child));state_before=rng.bit_generator.state
        groups=defaultdict(list)
        for r in eligible_by_k[k]:groups[(r['node_id'],r['start_date'])].append(r)
        group_keys=sorted(groups);queues={}
        for g in group_keys:
            ordered=sorted(groups[g],key=lambda r:r['t0']);permutation=rng.permutation(len(ordered))
            queues[g]=deque(ordered[int(i)] for i in permutation)
            for rank,r in enumerate(queues[g]):r['within_group_shuffle_rank']=rank
        order=[group_keys[int(i)] for i in rng.permutation(len(group_keys))]
        for rank,g in enumerate(order):
            for r in queues[g]:r['sampler_group_rank']=rank
        occupied=defaultdict(list);count=0;attempt=0
        while count<300 and any(queues.values()):
            for g in order:
                if count>=300:break
                while queues[g]:
                    r=queues[g].popleft();attempt+=1;r['sampler_attempt_order']=attempt
                    overlap=any(not(r['right_endpoint']<a or r['left_endpoint']>b) for a,b in occupied[r['node_id']])
                    if overlap:r['selection_status']='OVERLAP_REJECTED';continue
                    r['selection_status']='SELECTED';count+=1
                    occupied[r['node_id']].append((r['left_endpoint'],r['right_endpoint']))
                    selected.append(r);break
        for q in queues.values():
            for r in q:r['selection_status']='CAP_REACHED_NOT_VISITED'
        selection_counts[k]=count
        rng_records.append(dict(K=k,spawn_key=list(child.spawn_key),entropy=child.entropy,group_count=len(order),selected_count=count,attempted_count=attempt,remaining_not_visited=sum(len(q) for q in queues.values()),state_before=state_before,state_after=rng.bit_generator.state))
    write_csv(out/'inputs/CANDIDATE_CATALOG.csv',catalog)
    dump(out/'inputs/SAMPLER_RNG.json',dict(numpy_version=np.__version__,generator='PCG64',seed=SEED,streams=rng_records))
    gap_rows=[];refs=[];contexts=[];tod_inputs=[];preds=[];target_support=[]
    for r in selected:
        k=r['K'];n=r['node_id'];d=datetime.fromisoformat(r['t0']);left=datetime.fromisoformat(r['left_endpoint']);right=datetime.fromisoformat(r['right_endpoint'])
        gid=f'G{k:02d}_{sum(x["K"]==k for x in gap_rows)+1:03d}'
        targets=[d+j*DELTA for j in range(k)]
        hidden_dates=sorted({x.strftime('%Y-%m-%d') for x in targets});context_dates=sorted({left.strftime('%Y-%m-%d'),right.strftime('%Y-%m-%d')}|set(hidden_dates))
        gap_rows.append(dict(gap_id=gid,candidate_id=r['candidate_id'],node_id=n,K=k,duration_h=k/4,t0=r['t0'],last_hidden=r['last_hidden'],left_endpoint=r['left_endpoint'],right_endpoint=r['right_endpoint'],start_date=r['start_date'],hidden_dates='|'.join(hidden_dates),context_dates='|'.join(context_dates),crosses_midnight=len(context_dates)>1,min_train_tod_count=r['min_train_tod_count'],min_other_node_count=r['min_other_node_count'],selection_order_within_length=sum(x['K']==k for x in gap_rows)+1))
        for role,x in [('LEFT_ENDPOINT',left),('RIGHT_ENDPOINT',right)]:
            v=raw[(n,x)];contexts.append(dict(gap_id=gid,role=role,node_id=n,slot_local=fmt(x),visible_speed_kmh=v['speed'],source_file=v['source_file'],source_row_number=v['source_row_number']))
        view=dict(K=k,left_speed=raw[(n,left)]['speed'],right_speed=raw[(n,right)]['speed'],train_tod=[],other_speeds=[])
        for j,x in enumerate(targets,1):
            tr=stats[(n,tod(x))];other=sorted((nn,v) for nn,v in at[x].items() if nn!=n)
            view['train_tod'].append(tr);view['other_speeds'].append([v['speed'] for nn,v in other])
            for nn,v in other:contexts.append(dict(gap_id=gid,role='CONTEMPORANEOUS_OTHER_NODE',node_id=nn,slot_local=fmt(x),visible_speed_kmh=v['speed'],source_file=v['source_file'],source_row_number=v['source_row_number']))
            tod_inputs.append(dict(gap_id=gid,target_index=j,node_id=n,target_time=fmt(x),tod_quarter_index=tod(x),train_observation_count=tr['count'],train_median_speed_kmh=tr['median']))
            target_support.append(dict(gap_id=gid,target_index=j,target_time=fmt(x),train_tod_count=tr['count'],other_node_count=len(other),other_node_ids='|'.join(nn for nn,v in other)))
            v=raw[(n,x)];refs.append(dict(gap_id=gid,node_id=n,K=k,target_index=j,target_time=fmt(x),hidden_provider_speed_kmh=v['speed'],source_file=v['source_file'],source_row_number=v['source_row_number']))
        prediction=reconstruct(view)
        for method,values in prediction.items():
            for j,(x,value) in enumerate(zip(targets,values),1):
                ok=math.isfinite(value)
                preds.append(dict(gap_id=gid,node_id=n,K=k,method=method,target_index=j,target_time=fmt(x),reconstructed_speed_kmh=value if ok else None,status='SUCCESS' if ok else 'FAILED',failure_reason='' if ok else 'NONFINITE_PREDICTION'))
    write_csv(out/'inputs/FROZEN_GAPS.csv',gap_rows,['gap_id','candidate_id','node_id','K','duration_h','t0','last_hidden','left_endpoint','right_endpoint','start_date','hidden_dates','context_dates','crosses_midnight','min_train_tod_count','min_other_node_count','selection_order_within_length'])
    write_csv(out/'inputs/ALLOWED_SPEED_CONTEXT.csv',contexts,['gap_id','role','node_id','slot_local','visible_speed_kmh','source_file','source_row_number'])
    write_csv(out/'inputs/FROZEN_TOD_INPUTS.csv',tod_inputs,['gap_id','target_index','node_id','target_time','tod_quarter_index','train_observation_count','train_median_speed_kmh'])
    write_csv(out/'inputs/TARGET_SUPPORT.csv',target_support,['gap_id','target_index','target_time','train_tod_count','other_node_count','other_node_ids'])
    write_csv(out/'reference/HIDDEN_PROVIDER_TARGETS.csv',refs,['gap_id','node_id','K','target_index','target_time','hidden_provider_speed_kmh','source_file','source_row_number'])
    write_csv(out/'results/POINT_PREDICTIONS.csv',preds,['gap_id','node_id','K','method','target_index','target_time','reconstructed_speed_kmh','status','failure_reason'])
    pr=pd.DataFrame(preds,columns=['gap_id','node_id','K','method','target_index','target_time','reconstructed_speed_kmh','status','failure_reason'])
    rf=pd.DataFrame(refs,columns=['gap_id','node_id','K','target_index','target_time','hidden_provider_speed_kmh','source_file','source_row_number'])
    scores=pr.merge(rf,on=['gap_id','node_id','K','target_index','target_time'],validate='many_to_one')
    scores['error_kmh']=scores.reconstructed_speed_kmh-scores.hidden_provider_speed_kmh
    scores['squared_error']=scores.error_kmh**2;scores['absolute_error_kmh']=scores.error_kmh.abs()
    write_csv(out/'results/POINT_SCORES.csv',scores)
    gap_metrics=[];completion=[];summary=[]
    common_by_k={}
    for k in KS:
        planned=[r for r in gap_rows if r['K']==k];complete_sets={}
        for method in METHODS:
            g=scores[(scores.K==k)&(scores.method==method)]
            complete_sets[method]={gid for gid,x in g.groupby('gap_id') if len(x)==k and (x.status=='SUCCESS').all()}
        common=set.intersection(*complete_sets.values())
        common_by_k[k]=common
        for method in METHODS:
            g=scores[(scores.K==k)&(scores.method==method)]
            complete=complete_sets[method]
            for gid,x in g.groupby('gap_id',sort=False):
                ok=gid in complete
                gap_metrics.append(dict(gap_id=gid,K=k,method=method,target_point_count=len(x),complete=ok,common_complete=gid in common,sse=float(x.squared_error.sum()) if ok else None,sum_absolute_error_kmh=float(x.absolute_error_kmh.sum()) if ok else None,mse=float(x.squared_error.mean()) if ok else None,rmse_kmh=float(np.sqrt(x.squared_error.mean())) if ok else None,mae_kmh=float(x.absolute_error_kmh.mean()) if ok else None))
            completion.append(dict(K=k,method=method,planned_gaps=len(planned),predicted_complete_gaps=len(complete),common_complete_gaps=len(common),failed_gaps=len(planned)-len(complete),completion_pct=100*len(complete)/len(planned) if planned else None,common_retention_pct=100*len(common)/len(planned) if planned else None,planned_target_points=len(planned)*k,common_target_points=len(common)*k))
            x=g[g.gap_id.isin(common)];ms=[r['rmse_kmh'] for r in gap_metrics if r['K']==k and r['method']==method and r['common_complete']]
            support=[r for r in planned if r['gap_id'] in common]
            summary.append(dict(K=k,duration_h=k/4,method=method,N_gaps=len(common),M_target_points=len(x),sse=float(x.squared_error.sum()) if len(x) else None,sum_absolute_error_kmh=float(x.absolute_error_kmh.sum()) if len(x) else None,pooled_rmse_kmh=float(np.sqrt(x.squared_error.mean())) if len(x) else None,pooled_mae_kmh=float(x.absolute_error_kmh.mean()) if len(x) else None,gap_rmse_median_kmh=float(np.median(ms)) if ms else None,gap_rmse_q25_kmh=float(np.quantile(ms,.25,method='linear')) if ms else None,gap_rmse_q75_kmh=float(np.quantile(ms,.75,method='linear')) if ms else None,node_count=len({r['node_id'] for r in support}),start_date_count=len({r['start_date'] for r in support}),hidden_date_count=len({d for r in support for d in r['hidden_dates'].split('|')}),context_date_count=len({d for r in support for d in r['context_dates'].split('|')}),cross_midnight_gaps=sum(r['crosses_midnight'] for r in support)))
    write_csv(out/'results/GAP_METRICS.csv',gap_metrics,['gap_id','K','method','target_point_count','complete','common_complete','sse','sum_absolute_error_kmh','mse','rmse_kmh','mae_kmh'])
    write_csv(out/'results/COMPLETION_COUNTS.csv',completion)
    write_csv(out/'results/METRICS_BY_LENGTH_METHOD.csv',summary)
    write_csv(out/'results/FAILED_PREDICTIONS.csv',pr[pr.status!='SUCCESS'])
    csummary=[];exclusions=[]
    for k in KS:
        rows=[r for r in catalog if r['K']==k];eg=eligible_by_k[k];sel=[r for r in gap_rows if r['K']==k]
        reasons=Counter(r['first_exclusion_reason'] for r in rows if not r['eligible'])
        for reason in FAIL_ORDER:exclusions.append(dict(K=k,reason=reason,exclusive_first_failure_count=reasons[reason],all_failure_flag_count=sum(reason in r['all_exclusion_reasons'].split('|') for r in rows)))
        csummary.append(dict(K=k,duration_h=k/4,initial_test_start_positions=len(rows),boundary_qualified=sum(r['boundary_pass'] for r in rows),eligible_candidates=len(eg),excluded_candidates=len(rows)-len(eg),maximum_nonoverlap_capacity=sum(r['maximum_nonoverlap_contexts'] for r in capacity if r['K']==k),selected_gaps=len(sel),sampler_overlap_rejected=sum(r['selection_status']=='OVERLAP_REJECTED' for r in eg),cap_not_visited=sum(r['selection_status']=='CAP_REACHED_NOT_VISITED' for r in eg),selected_nodes=len({r['node_id'] for r in sel}),selected_start_dates=len({r['start_date'] for r in sel}),selected_context_dates=len({d for r in sel for d in r['context_dates'].split('|')}),cross_midnight_gaps=sum(r['crosses_midnight'] for r in sel)))
        check(f'catalog_gate_partition_K{k}',len(eg)+sum(reasons.values()),51*384)
        check(f'cap_K{k}',len(sel)<=300,True)
        check(f'common_complete_K{k}',len(common_by_k[k]),len(sel))
        for method in METHODS:
            keyset={(r['gap_id'],r['target_time']) for r in preds if r['K']==k and r['method']==method}
            check(f'method_target_keys_K{k}:{method}',keyset=={(r['gap_id'],r['target_time']) for r in refs if r['K']==k},True)
    write_csv(out/'inputs/CANDIDATE_EXCLUSIONS.csv',exclusions)
    write_csv(out/'inputs/CANDIDATE_SUPPORT_SUMMARY.csv',csummary)
    write_csv(out/'inputs/SELECTED_SUPPORT_BY_NODE_DATE.csv',pd.DataFrame(gap_rows,columns=['K','node_id','start_date','gap_id']).groupby(['K','node_id','start_date']).gap_id.size().rename('selected_gaps').reset_index())
    check('train_statistics_unchanged_after_scoring',sha(out/'inputs/TRAIN_TOD_STATS.csv'),train_stats_hash)
    check('planned_score_points',len(refs),sum(r['K'] for r in gap_rows))
    check('four_method_points',len(preds),4*len(refs))
    check('failed_predictions',int((pr.status!='SUCCESS').sum()),0)
    targetkeys={(r['gap_id'],r['node_id'],r['target_time']) for r in refs}
    check('hidden_target_absent_from_allowed_speed_context',sum((r['gap_id'],r['node_id'],r['slot_local']) in targetkeys for r in contexts),0)
    for r in lock:
        r['sha256_after']=sha(Path(r['path']));check('input_unchanged:'+Path(r['path']).name,r['sha256_after'],r['sha256_before'])
    write_csv(out/'INPUT_LOCK.csv',lock);write_csv(out/'qa/BUILD_QA.csv',qa)
    dump(out/'RESULT_SUMMARY.json',dict(candidate_support=csummary,metrics=summary,training_TOD=dict(groups=len(ts),min_count=int(ts.observation_count.min()),max_count=int(ts.observation_count.max()),insufficient_groups=int((ts.observation_count<3).sum()),frozen_stats_sha256=train_stats_hash),total_selected_experiments=len(gap_rows),point_reference_count=len(refs),total_method_predictions=len(preds),validation_tuning_performed=False))
    dump(out/'RUN_CONTEXT.json',dict(completed_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,executable=sys.executable,pandas=pd.__version__,numpy=np.__version__,platform=platform.platform(),script_sha256=sha(Path(__file__)),output_dir=str(out)))
    print(json.dumps(dict(candidate_support=csummary,metrics=summary,build_QA_count=len(qa),failed=0),ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,required=True)
    main(parser.parse_args().output_dir)
