"""Independent raw/CSV reconstruction and sampling replay, no build import.
Uses stdlib for medians/scoring and dynamic-programming interval capacity;
Numpy is used only to replay the mandated PCG64 random stream.
"""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
import csv, hashlib, json, math, statistics, sys
import numpy as np

OUT=Path(sys.argv[1]).resolve()
FREEZE=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\TomTom_Core_Freeze_20261004')
KS=[1,4,12,24];METHODS=['Linear','LOCF','Train-TOD median','Spatial median']
START=datetime(2025,12,28);END=datetime(2026,1,1);STEP=timedelta(minutes=15)
REASONS=['OUTSIDE_TEST_CONTEXT','TARGET_NATURAL_MISSING','ENDPOINT_MISSING','TRAIN_TOD_SUPPORT_LT3','OTHER_NODE_SUPPORT_LT3']
TOL=1e-10;QA=[]
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def fmt(d):return d.strftime('%Y-%m-%d %H:%M:%S')
def tod(d):return d.hour*4+d.minute//15
def qa(name,ok,detail=''):QA.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=str(detail)))
def index(rows,keys,name):
    d={tuple(r[k] for k in keys):r for r in rows};qa(name+':unique_keys',len(d)==len(rows),len(rows));return d
def close(name,pairs):
    pairs=list(pairs);errs=[];missing=0
    for actual,expected in pairs:
        if expected is None:missing+=int(actual!='')
        else:
            try:errs.append(abs(float(actual)-expected))
            except (ValueError,TypeError):missing+=1
    err=max(errs,default=0)
    qa(name,missing==0 and err<=TOL,dict(n=len(pairs),max_abs_error=err,missing_mismatch=missing,tolerance=TOL))
def quantile(x,p):
    x=sorted(x);j=(len(x)-1)*p;a=math.floor(j);b=math.ceil(j)
    return x[a]+(x[b]-x[a])*(j-a)

def main():
    config=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    qa('confirmed_protocol',config['lengths_K']==KS and config['seed']==20261006 and config['generator']=='PCG64' and config['train_tod_min_observations']==3 and config['other_node_min_observations']==3 and config['maximum_selected_gaps_per_length']==300 and not config['prediction_clipping'] and not config['fallback'] and not config['bootstrap'] and not config['forecasting'])
    locks=read(OUT/'INPUT_LOCK.csv')
    qa('inputs_before_after_current_unchanged',all(digest(Path(r['path']))==r['sha256_before']==r['sha256_after'] for r in locks))
    raw=read(FREEZE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv')
    rawidx=index(raw,['node_id','interval_timestamp_local'],'frozen_raw')
    nodes=sorted({r['node_id'] for r in raw})
    speeds={k:float(r['current_speed_kmh']) for k,r in rawidx.items()}
    network=defaultdict(dict);train_values=defaultdict(list)
    for (n,t),v in speeds.items():
        network[t][n]=v;d=datetime.fromisoformat(t)
        if datetime(2025,12,8)<=d<datetime(2025,12,24):train_values[(n,tod(d))].append(v)
    stats={(n,i):(len(train_values[(n,i)]),statistics.median(train_values[(n,i)]) if train_values[(n,i)] else None) for n in nodes for i in range(96)}
    training=read(OUT/'inputs/TRAIN_TOD_MEMBERSHIP.csv')
    train_keys={k for k in speeds if '2025-12-08 00:00:00'<=k[1]<'2025-12-24 00:00:00'}
    qa('training_membership_keys_exact_no_validation_test',len(training)==len(train_keys)==59009 and {(r['node_id'],r['interval_timestamp_local']) for r in training}==train_keys)
    close('training_membership_speeds',[(r['current_speed_kmh'],speeds[(r['node_id'],r['interval_timestamp_local'])]) for r in training])
    qa('training_membership_source_trace',all(r['source_file']==rawidx[(r['node_id'],r['interval_timestamp_local'])]['source_file'] and r['source_row_number']==rawidx[(r['node_id'],r['interval_timestamp_local'])]['source_row_number'] for r in training))
    ts=read(OUT/'inputs/TRAIN_TOD_STATS.csv')
    ti=index(ts,['node_id','tod_quarter_index'],'training_TOD')
    qa('training_TOD_complete_grid',set(ti)=={(n,str(i)) for n in nodes for i in range(96)})
    qa('training_TOD_counts_and_eligibility',all(int(r['observation_count'])==stats[(n,int(i))][0] and (r['reference_qualified']=='True')==(stats[(n,int(i))][0]>=3) for (n,i),r in ti.items()))
    close('training_TOD_original_medians',[(r['median_speed_kmh'],stats[(n,int(i))][1]) for (n,i),r in ti.items()])
    partitions=read(OUT/'inputs/PARTITION_COUNTS.csv')
    counts={'train':59009,'validation':16128,'test':15792}
    qa('partition_counts',len(partitions)==3 and all(int(r['raw_rows'])==counts[r['partition']] for r in partitions))
    # Recreate entire candidate universe and every gate from raw keys, not exported flags.
    candidates=read(OUT/'inputs/CANDIDATE_CATALOG.csv')
    ci=index(candidates,['candidate_id'],'candidate_catalog')
    exp={};eligible={k:[] for k in KS};candidate_gates=True;gate_counts=True
    for k in KS:
        for n in nodes:
            for i in range(384):
                d=START+i*STEP;left=d-STEP;right=d+k*STEP;targets=[d+j*STEP for j in range(k)]
                cid=f'K{k:02d}:{n}:{d.strftime("%Y%m%dT%H%M")}'
                fail=[];details={}
                if left<START or right>=END:fail=[REASONS[0]]
                else:
                    missing=sum((n,fmt(x)) not in speeds for x in targets)
                    lp=(n,fmt(left)) in speeds;rp=(n,fmt(right)) in speeds
                    tr=min(stats[(n,tod(x))][0] for x in targets)
                    other=min(len(network[fmt(x)])-int(n in network[fmt(x)]) for x in targets)
                    details=dict(target_missing_count=missing,left_observed=lp,right_observed=rp,min_train_tod_count=tr,min_other_node_count=other)
                    if missing:fail.append(REASONS[1])
                    if not(lp and rp):fail.append(REASONS[2])
                    if tr<3:fail.append(REASONS[3])
                    if other<3:fail.append(REASONS[4])
                e=dict(candidate_id=cid,K=k,node_id=n,t0=fmt(d),left_endpoint=fmt(left),right_endpoint=fmt(right),start_date=d.strftime('%Y-%m-%d'),fail=fail,details=details)
                exp[cid]=e
                if not fail:eligible[k].append(e)
                r=ci.get((cid,))
                candidate_gates &= r is not None and (r['eligible']=='True')==(not fail) and r['first_exclusion_reason']==(fail[0] if fail else '') and r['all_exclusion_reasons']=='|'.join(fail) and r['t0']==fmt(d) and r['left_endpoint']==fmt(left) and r['right_endpoint']==fmt(right)
                if r:
                    for field,v in details.items():
                        gate_counts &= r[field]==str(v) if isinstance(v,bool) else int(r[field])==v
    qa('candidate_universe_exact',len(ci)==51*384*4 and set(k[0] for k in ci)==set(exp))
    qa('candidate_all_eligibility_rules_exact',candidate_gates)
    qa('candidate_support_counts_exact',gate_counts)
    exclusions=read(OUT/'inputs/CANDIDATE_EXCLUSIONS.csv')
    qa('exclusion_exclusive_and_all_flags',len(exclusions)==20 and all(int(r['exclusive_first_failure_count'])==sum(e['K']==int(r['K']) and bool(e['fail']) and e['fail'][0]==r['reason'] for e in exp.values()) and int(r['all_failure_flag_count'])==sum(e['K']==int(r['K']) and r['reason'] in e['fail'] for e in exp.values()) for r in exclusions))
    # Independent maximum capacity via DP over test slots, including shared-endpoint exclusion.
    capacity={}
    for k in KS:
        for n in nodes:
            end_to_start={int((datetime.fromisoformat(e['right_endpoint'])-START)/STEP):int((datetime.fromisoformat(e['left_endpoint'])-START)/STEP) for e in eligible[k] if e['node_id']==n}
            best=[]
            for end in range(384):
                value=best[-1] if best else 0
                if end in end_to_start:
                    left=end_to_start[end];value=max(value,1+(best[left-1] if left>0 else 0))
                best.append(value)
            capacity[(k,n)]=best[-1]
    caprows=read(OUT/'inputs/NONOVERLAP_CAPACITY_BY_NODE.csv')
    qa('maximum_nonoverlap_capacity_DP',len(caprows)==204 and all(int(r['maximum_nonoverlap_contexts'])==capacity[(int(r['K']),r['node_id'])] for r in caprows))
    witnesses=read(OUT/'inputs/NONOVERLAP_CAPACITY_WITNESS.csv')
    wc=Counter((int(r['K']),r['node_id']) for r in witnesses)
    witness_ok=all(wc[k]==v for k,v in capacity.items())
    for key in capacity:
        x=sorted((r for r in witnesses if (int(r['K']),r['node_id'])==key),key=lambda r:r['left_endpoint'])
        witness_ok &= all(not exp[r['candidate_id']]['fail'] for r in x) and all(a['right_endpoint']<b['left_endpoint'] for a,b in zip(x,x[1:]))
    qa('maximum_capacity_witness_valid',witness_ok)
    # Replay PCG64 using array cursors instead of builder queues.
    children=np.random.SeedSequence(20261006).spawn(4);selected_expected={};expected_status={};rng_states={}
    for k,child in zip(KS,children):
        rng=np.random.Generator(np.random.PCG64(child));groups=defaultdict(list)
        for e in eligible[k]:groups[(e['node_id'],e['start_date'])].append(e)
        keys=sorted(groups);permuted={}
        for g in keys:
            members=sorted(groups[g],key=lambda e:e['t0']);permuted[g]=[members[int(i)] for i in rng.permutation(len(members))]
        order=[keys[int(i)] for i in rng.permutation(len(keys))];cursor={g:0 for g in keys};chosen=[];occupied=defaultdict(list)
        while len(chosen)<300 and any(cursor[g]<len(permuted[g]) for g in keys):
            for g in order:
                if len(chosen)==300:break
                while cursor[g]<len(permuted[g]):
                    e=permuted[g][cursor[g]];cursor[g]+=1
                    intersects=any(e['left_endpoint']<=old['right_endpoint'] and old['left_endpoint']<=e['right_endpoint'] for old in occupied[e['node_id']])
                    if intersects:expected_status[e['candidate_id']]='OVERLAP_REJECTED';continue
                    chosen.append(e);occupied[e['node_id']].append(e);expected_status[e['candidate_id']]='SELECTED';break
        for g in keys:
            for e in permuted[g][cursor[g]:]:expected_status[e['candidate_id']]='CAP_REACHED_NOT_VISITED'
        selected_expected[k]=chosen;rng_states[k]=rng.bit_generator.state
    gaps=read(OUT/'inputs/FROZEN_GAPS.csv');gi=index(gaps,['gap_id'],'frozen_gaps')
    qa('seeded_selection_order_reproduced',all([r['candidate_id'] for r in gaps if int(r['K'])==k]==[e['candidate_id'] for e in selected_expected[k]] for k in KS))
    qa('sampler_candidate_dispositions',all(r['selection_status']==(expected_status[r['candidate_id']] if r['eligible']=='True' else 'INELIGIBLE') for r in candidates))
    rng=json.loads((OUT/'inputs/SAMPLER_RNG.json').read_text(encoding='utf-8'))
    qa('sampler_final_rng_state',all(r['state_after']==rng_states[r['K']] and r['spawn_key']==[KS.index(r['K'])] for r in rng['streams']))
    nonoverlap=True;bounds=True;maximal=True
    for k in KS:
        selected=[r for r in gaps if int(r['K'])==k]
        for n in nodes:
            rr=sorted((r for r in selected if r['node_id']==n),key=lambda r:r['left_endpoint'])
            nonoverlap &= all(a['right_endpoint']<b['left_endpoint'] for a,b in zip(rr,rr[1:]))
        bounds &= all(fmt(START)<=r['left_endpoint']<r['t0']<=r['last_hidden']<r['right_endpoint']<fmt(END) for r in selected)
        if len(selected)<300:
            for e in eligible[k]:
                maximal &= any(e['node_id']==r['node_id'] and e['left_endpoint']<=r['right_endpoint'] and r['left_endpoint']<=e['right_endpoint'] for r in selected)
    qa('selected_closed_contexts_do_not_overlap',nonoverlap)
    qa('selected_contexts_entirely_within_test',bounds)
    qa('under_cap_sampler_is_maximal_not_asserted_maximum',maximal)
    refs=read(OUT/'reference/HIDDEN_PROVIDER_TARGETS.csv')
    ri=index(refs,['gap_id','target_time'],'hidden_reference')
    expected_targets={(r['gap_id'],fmt(datetime.fromisoformat(r['t0'])+j*STEP)) for r in gaps for j in range(int(r['K']))}
    qa('hidden_reference_keys_exact_K_per_gap',set(ri)==expected_targets)
    qa('hidden_reference_source_provenance',all((r['node_id'],r['target_time']) in rawidx and r['source_file']==rawidx[(r['node_id'],r['target_time'])]['source_file'] and r['source_row_number']==rawidx[(r['node_id'],r['target_time'])]['source_row_number'] for r in refs))
    close('hidden_reference_is_original_provider_speed',[(r['hidden_provider_speed_kmh'],speeds[(r['node_id'],r['target_time'])]) for r in refs])
    context=read(OUT/'inputs/ALLOWED_SPEED_CONTEXT.csv')
    ctxt=index(context,['gap_id','role','node_id','slot_local'],'allowed_context')
    expected_context={};ref_support={}
    for r in gaps:
        gid=r['gap_id'];n=r['node_id'];k=int(r['K']);d=datetime.fromisoformat(r['t0'])
        for role,x in [('LEFT_ENDPOINT',r['left_endpoint']),('RIGHT_ENDPOINT',r['right_endpoint'])]:expected_context[(gid,role,n,x)]=speeds[(n,x)]
        for j in range(k):
            t=fmt(d+j*STEP);others={nn:v for nn,v in network[t].items() if nn!=n}
            ref_support[(gid,t)]=others
            for nn,v in others.items():expected_context[(gid,'CONTEMPORANEOUS_OTHER_NODE',nn,t)]=v
    qa('allowed_context_members_exact_original_visible_only',set(ctxt)==set(expected_context))
    qa('allowed_input_schema_no_ancillary_fields',set(context[0])=={'gap_id','role','node_id','slot_local','visible_speed_kmh','source_file','source_row_number'} if context else not gaps)
    qa('hidden_targets_not_in_allowed_context',all((r['gap_id'],r['slot_local']) not in ri or r['node_id']!=ri[(r['gap_id'],r['slot_local'])]['node_id'] for r in context))
    close('allowed_context_original_speeds',[(r['visible_speed_kmh'],expected_context[key]) for key,r in ctxt.items()])
    qa('allowed_context_source_provenance',all(r['source_file']==rawidx[(r['node_id'],r['slot_local'])]['source_file'] and r['source_row_number']==rawidx[(r['node_id'],r['slot_local'])]['source_row_number'] for r in context))
    frozen_tod=read(OUT/'inputs/FROZEN_TOD_INPUTS.csv')
    fi=index(frozen_tod,['gap_id','target_time'],'frozen_TOD_input')
    qa('frozen_TOD_input_keys',set(fi)==expected_targets)
    close('frozen_TOD_input_only_training_medians',[(r['train_median_speed_kmh'],stats[(r['node_id'],tod(datetime.fromisoformat(r['target_time'])))][1]) for r in frozen_tod])
    qa('frozen_TOD_input_support',all(int(r['train_observation_count'])==stats[(r['node_id'],tod(datetime.fromisoformat(r['target_time'])))][0]>=3 for r in frozen_tod))
    support=read(OUT/'inputs/TARGET_SUPPORT.csv')
    qa('target_other_node_support_and_lists',len(support)==len(expected_targets) and all(int(r['other_node_count'])==len(ref_support[(r['gap_id'],r['target_time'])])>=3 and r['other_node_ids']=='|'.join(sorted(ref_support[(r['gap_id'],r['target_time'])])) for r in support))
    # Derive method predictions entirely from exported allowed input view, no hidden y.
    predicted={};expected_errors={};no_hidden_needed=True
    for r in gaps:
        gid=r['gap_id'];n=r['node_id'];k=int(r['K']);d=datetime.fromisoformat(r['t0'])
        l=float(ctxt[(gid,'LEFT_ENDPOINT',n,r['left_endpoint'])]['visible_speed_kmh']);rr=float(ctxt[(gid,'RIGHT_ENDPOINT',n,r['right_endpoint'])]['visible_speed_kmh'])
        for j in range(k):
            t=fmt(d+j*STEP)
            other=[float(ctxt[(gid,'CONTEMPORANEOUS_OTHER_NODE',nn,t)]['visible_speed_kmh']) for nn in ref_support[(gid,t)]]
            vals={'Linear':((k-j)*l+(j+1)*rr)/(k+1),'LOCF':l,'Train-TOD median':float(fi[(gid,t)]['train_median_speed_kmh']),'Spatial median':statistics.median(other)}
            for method,v in vals.items():predicted[(gid,method,t)]=v
    predrows=read(OUT/'results/POINT_PREDICTIONS.csv');pi=index(predrows,['gap_id','method','target_time'],'predictions')
    qa('all_four_methods_identical_complete_targets',set(pi)=={(g,m,t) for g,t in expected_targets for m in METHODS})
    qa('all_predictions_success_no_failure',all(r['status']=='SUCCESS' and r['failure_reason']=='' for r in predrows))
    close('predictions_from_masked_allowed_input_only',[(r['reconstructed_speed_kmh'],predicted[key]) for key,r in pi.items()])
    for key,v in predicted.items():expected_errors[key]=v-float(ri[(key[0],key[2])]['hidden_provider_speed_kmh'])
    points=read(OUT/'results/POINT_SCORES.csv');si=index(points,['gap_id','method','target_time'],'point_scores')
    qa('point_score_keys_equal_predictions',set(si)==set(pi))
    close('point_error_recomputed',[(r['error_kmh'],expected_errors[key]) for key,r in si.items()])
    close('point_squared_error_recomputed',[(r['squared_error'],expected_errors[key]**2) for key,r in si.items()])
    close('point_absolute_error_recomputed',[(r['absolute_error_kmh'],abs(expected_errors[key])) for key,r in si.items()])
    # SSE export roundoff is evaluated relative to scale; prediction/error tolerance stays absolute.
    gap_errors=defaultdict(list)
    for (gid,m,t),e in expected_errors.items():gap_errors[(gid,m)].append(e)
    gm=read(OUT/'results/GAP_METRICS.csv');mi=index(gm,['gap_id','method'],'gap_metrics')
    qa('gap_metrics_exact_complete_keys',set(mi)==set(gap_errors) and all(r['complete']=='True' and r['common_complete']=='True' and int(r['target_point_count'])==len(gap_errors[key]) for key,r in mi.items()))
    expected_gap_rmse={key:math.sqrt(statistics.mean(e*e for e in errors)) for key,errors in gap_errors.items()}
    close('gap_RMSE_independent',[(r['rmse_kmh'],expected_gap_rmse[key]) for key,r in mi.items()])
    close('gap_MAE_independent',[(r['mae_kmh'],statistics.mean(abs(e) for e in gap_errors[key])) for key,r in mi.items()])
    metrics=read(OUT/'results/METRICS_BY_LENGTH_METHOD.csv')
    checks=defaultdict(list);sse_ok=True;sample_counts=True
    for r in metrics:
        k=int(r['K']);m=r['method'];gg=[g for g in gaps if int(g['K'])==k];errors=[e for (gid,method,t),e in expected_errors.items() if method==m and int(gi[(gid,)]['K'])==k]
        gr=[expected_gap_rmse[(g['gap_id'],m)] for g in gg]
        sample_counts &= int(r['N_gaps'])==len(gg) and int(r['M_target_points'])==len(gg)*k==len(errors) and int(r['node_count'])==len({g['node_id'] for g in gg}) and int(r['start_date_count'])==len({g['start_date'] for g in gg})
        if errors:
            vals=dict(pooled_rmse_kmh=math.sqrt(statistics.mean(e*e for e in errors)),pooled_mae_kmh=statistics.mean(abs(e) for e in errors),gap_rmse_median_kmh=statistics.median(gr),gap_rmse_q25_kmh=quantile(gr,.25),gap_rmse_q75_kmh=quantile(gr,.75))
            for name,v in vals.items():checks[name].append((r[name],v))
            sse=sum(e*e for e in errors);sse_ok &= math.isclose(float(r['sse']),sse,rel_tol=1e-12,abs_tol=TOL)
        else:
            for name in ['pooled_rmse_kmh','pooled_mae_kmh','gap_rmse_median_kmh','gap_rmse_q25_kmh','gap_rmse_q75_kmh']:checks[name].append((r[name],None))
    qa('summary_N_M_and_node_date_support',sample_counts and len(metrics)==16)
    qa('summary_SSE_independent_relative_tolerance',sse_ok,'rel_tol=1e-12, abs_tol=1e-10; only accumulated SSE')
    for name,pairs in checks.items():close('summary_'+name,pairs)
    completions=read(OUT/'results/COMPLETION_COUNTS.csv')
    qa('completion_counts_no_silent_dropping',len(completions)==16 and all(int(r['planned_gaps'])==int(r['predicted_complete_gaps'])==int(r['common_complete_gaps'])==sum(int(g['K'])==int(r['K']) for g in gaps) and int(r['failed_gaps'])==0 and int(r['common_target_points'])==int(r['common_complete_gaps'])*int(r['K']) for r in completions))
    qa('failed_prediction_table_empty',not read(OUT/'results/FAILED_PREDICTIONS.csv'))
    supp=read(OUT/'inputs/CANDIDATE_SUPPORT_SUMMARY.csv')
    qa('candidate_support_summary_reconciliation',len(supp)==4 and all(int(r['initial_test_start_positions'])==19584 and int(r['eligible_candidates'])==len(eligible[int(r['K'])]) and int(r['maximum_nonoverlap_capacity'])==sum(capacity[(int(r['K']),n)] for n in nodes) and int(r['selected_gaps'])==len(selected_expected[int(r['K'])]) for r in supp))
    build=read(OUT/'qa/BUILD_QA.csv');qa('build_checks_all_PASS',all(r['status']=='PASS' for r in build),len(build))
    with (OUT/'qa/INDEPENDENT_QA.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['check','status','detail']);w.writeheader();w.writerows(QA)
    report=dict(completed_utc=datetime.now(timezone.utc).isoformat(),verifier_sha256=digest(Path(__file__)),python=sys.version,numpy_for_sampling_replay=np.__version__,check_count=len(QA),failed_count=sum(r['status']=='FAIL' for r in QA),checks=QA)
    (OUT/'qa/INDEPENDENT_QA.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(check_count=len(QA),failed=[r for r in QA if r['status']=='FAIL']),ensure_ascii=False,indent=2))
    if report['failed_count']:raise SystemExit(1)

if __name__=='__main__':main()
