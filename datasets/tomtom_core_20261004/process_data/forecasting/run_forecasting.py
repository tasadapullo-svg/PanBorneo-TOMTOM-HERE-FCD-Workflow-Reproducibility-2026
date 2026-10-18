"""Execute the confirmed record-time-constrained retrospective forecast benchmark.
No plotting, source edits, input imputation, target clipping, or train+validation refit.
"""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,math,os,platform,shutil,sys,traceback
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
import numpy as np
import pandas as pd
import scipy,sklearn
from sklearn.linear_model import Ridge

ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
CORE=ROOT/'outputs/TomTom_Core_Freeze_20261004'
B06=ROOT/'outputs/Manuscript_Execution_20261007_b06_001243Z/figure7a_review_forecast_admission'
HANDOFF=ROOT/'outputs/Manuscript_Preparation_20261006/论文写作交接与结果证据清单.md'
OUT=Path(__file__).resolve().parent
TRAFFIC=CORE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv'
METHODS=['Persistence','Seasonal24','Ridge'];ALPHAS=[.1,1,10,100,1000]
ROLES=['lag1','lag2','lag3','lag4','seasonal'];PARTS=['train','validation','test'];LEVELS=['Overall','Low','Medium','High']
FMT='%Y-%m-%d %H:%M:%S';QA=[];LOCK=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,x):pd.DataFrame(x).to_csv(p,index=False,encoding='utf-8-sig',float_format='%.17g',date_format=FMT)
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def check(name,ok,detail=''):
    QA.append(dict(check=name,status='PASS' if bool(ok) else 'FAIL',detail=str(detail)))
    if not ok:raise AssertionError(name+': '+str(detail))
def locked(p,expected='',role=''):
    actual=sha(p)
    if expected:check('hash:'+str(p.name),actual==expected)
    LOCK.append(dict(path=str(p),role=role,bytes=p.stat().st_size,expected_sha256=expected,sha256_before=actual))
def metric(yhat,y):
    e=np.asarray(yhat,dtype=float)-np.asarray(y,dtype=float);n=len(e)
    return dict(N=n,mae_kmh=math.fsum(float(abs(v)) for v in e)/n,rmse_kmh=math.sqrt(math.fsum(float(v*v) for v in e)/n))
def key_index(frame):return pd.MultiIndex.from_frame(frame[['node_id','origin']])

def main():
    start=datetime.now(timezone.utc).isoformat()
    if (OUT/'CONFIG.json').exists():raise RuntimeError('Refusing to overwrite a previous run')
    for directory in ['inputs','features','models','predictions','validation','results','qa']: (OUT/directory).mkdir()
    locked(CORE/'SHA256_MANIFEST.csv','b38f799858a7af711a81e217e66390d733ae53c53bc2367cf01c988271116111','frozen manifest')
    for r in read(CORE/'SHA256_MANIFEST.csv'):locked(CORE/r['file'],r['sha256'],'frozen payload byte identity')
    locked(B06/'OUTPUT_MANIFEST.csv',role='previous admission output manifest')
    for r in read(B06/'OUTPUT_MANIFEST.csv'):locked(B06/r['file'],r['sha256'],'prior complete admission payload byte identity')
    locked(HANDOFF,role='confirmed protocol section 12')
    prior=json.loads((B06/'INDEPENDENT_QA.json').read_text(encoding='utf-8'))
    check('prior_admission_independent_QA',prior['check_count']==154 and prior['failed_count']==0 and prior['checked_candidate_rows']==352512)
    admission=json.loads((B06/'CONFIG.json').read_text(encoding='utf-8'))
    runtime=json.loads((B06/'EXISTING_MODEL_RUNTIME.json').read_text(encoding='utf-8'))
    check('same_existing_runtime',str(Path(sys.executable)).lower()==runtime['executable'].lower() and np.__version__==runtime['numpy'] and sklearn.__version__==runtime['sklearn'] and scipy.__version__==runtime['scipy'] and pd.__version__==runtime['pandas'])
    node_registry=sorted(pd.read_csv(CORE/'tomtom_node_master_51.csv').node_id.tolist())
    names=[role+'_speed_kmh' for role in ROLES]+['origin_clock_sin','origin_clock_cos']+['weekday_'+str(i) for i in range(7)]+['node_'+node for node in node_registry]
    cfg={k:v for k,v in admission.items() if k not in ['no_training_or_predictions','model_selection_not_performed']}
    cfg.update(methods=METHODS,alpha_candidates=ALPHAS,ridge_parameters=Ridge(fit_intercept=True,positive=False,solver='svd').get_params(),ridge_features=names,feature_count=len(names),speed_scaling='five columns, fitted on each H scorable training set; population sd ddof=0; constant scale=1',calendar_encoding='minute-of-local-day sin/cos, weekday Monday=0; 7 and 51 full indicators; non-speed features unscaled',alpha_selection='minimum common validation MAE; choose largest alpha within minimum+1e-12',refit_train_plus_validation=False,test_adaptive_training=False,prediction_clipping=False,bootstrap=False,confidence_intervals=False,reference_is_ground_truth=False,training_weights='all rows equal; strata are not features or weights',prediction_reference_isolation='write all issuable predictions before attaching references for that H',user_figure_preference='text instructions and actual CSV only; no generated plots')
    dump(OUT/'CONFIG.json',cfg)
    for name in ['TRAINING_AVAILABILITY_STRATA.csv','SAMPLE_SUPPORT_SUMMARY.csv','STRATIFIED_SUPPORT_SUMMARY.csv','EXCLUSION_COUNTS.csv','OBSERVATION_RECORD_INDEX.csv','TEST_COMMON_ORIGINS_ALL_H.csv']:
        shutil.copy2(B06/name,OUT/'inputs'/name);check('copy_byte_identity:'+name,sha(OUT/'inputs'/name)==sha(B06/name))
    fields=['node_id','interval_timestamp_local','capture_time_local','current_speed_kmh','raw_observed_flag','imputed_flag','source_file','source_row_number']
    observations=pd.read_csv(TRAFFIC,usecols=fields);observations.index=np.arange(1,len(observations)+1)
    observations.index.name='frozen_record_id'
    observations['interval_timestamp_local']=pd.to_datetime(observations.interval_timestamp_local,format=FMT)
    observations['capture_time_local']=pd.to_datetime(observations.capture_time_local,format=FMT)
    check('raw_traffic_identity',len(observations)==90929 and not observations.duplicated(['node_id','interval_timestamp_local']).any())
    check('all_original_finite',(observations.raw_observed_flag=='YES').all() and (observations.imputed_flag=='NO').all() and np.isfinite(observations.current_speed_kmh).all())
    source_speed=observations.current_speed_kmh.to_dict()
    support=pd.read_csv(B06/'SAMPLE_SUPPORT_SUMMARY.csv');layer_support=pd.read_csv(B06/'STRATIFIED_SUPPORT_SUMMARY.csv')
    availability=pd.read_csv(B06/'TRAINING_AVAILABILITY_STRATA.csv').set_index('node_id')
    all_test=[];completion=[];selection=[];coefficients=[];training_records=[]
    for H in [1,3,6]:
        print(f'H={H}: building original observed features',flush=True)
        frame=pd.read_csv(B06/f'samples/H{H}_ISSUABLE_KEYS.csv',parse_dates=['origin','target'])
        check(f'issuable_unique:H{H}',not frame.duplicated(['node_id','origin']).any())
        check(f'fixed_strata:H{H}',(frame.stratum==frame.node_id.map(availability.stratum)).all())
        for role in ROLES:
            record=observations.loc[frame[role+'_record_id']].reset_index()
            offset=-15*(ROLES.index(role)+1) if role!='seasonal' else H*60-1440
            check(f'exact_original_slot:H{H}:{role}',(record.node_id.to_numpy()==frame.node_id.to_numpy()).all() and (record.interval_timestamp_local.to_numpy()==(frame.origin+pd.Timedelta(minutes=offset)).to_numpy()).all())
            check(f'capture_visible:H{H}:{role}',(record.capture_time_local.to_numpy()<=frame.origin.to_numpy()).all())
            frame[role+'_speed_kmh']=record.current_speed_kmh.to_numpy()
            frame[role+'_capture']=record.capture_time_local.to_numpy()
        frame['origin_minute']=frame.origin.dt.hour*60+frame.origin.dt.minute;frame['weekday']=frame.origin.dt.dayofweek
        raw=frame[[role+'_speed_kmh' for role in ROLES]].to_numpy(dtype=np.float64)
        reference_keys=pd.read_csv(B06/f'samples/H{H}_SCORABLE_KEYS.csv',parse_dates=['origin','target'])
        check(f'score_keys_unique:H{H}',not reference_keys.duplicated(['node_id','origin']).any())
        reference_by_key=reference_keys.set_index(['node_id','origin'])
        idx=key_index(frame);reference_ids=reference_by_key.reference_record_id.reindex(idx).to_numpy()
        train_mask=(frame.partition.to_numpy()=='train')&np.isfinite(reference_ids)
        val_mask=(frame.partition.to_numpy()=='validation')&np.isfinite(reference_ids)
        target_train=observations.loc[reference_ids[train_mask].astype(int)]
        target_val=observations.loc[reference_ids[val_mask].astype(int)]
        for part,mask,target in [('train',train_mask,target_train),('validation',val_mask,target_val)]:
            end=pd.Timestamp(admission['partitions_left_closed_right_open'][part][1])
            check(f'labels_before_cutoff:H{H}:{part}',(target.capture_time_local<end).all() and (target.capture_time_local.to_numpy()>frame.loc[mask,'origin'].to_numpy()).all() and (target.interval_timestamp_local.to_numpy()==frame.loc[mask,'target'].to_numpy()).all() and (target.node_id.to_numpy()==frame.loc[mask,'node_id'].to_numpy()).all())
            expected=int(support.loc[(support.H_h==H)&(support.partition==part),'scorable'].iloc[0]);check(f'fit_support:H{H}:{part}',int(mask.sum())==expected)
        mean=raw[train_mask].mean(axis=0);sd=raw[train_mask].std(axis=0,ddof=0);scale=np.where(sd==0,1.,sd)
        clock=2*np.pi*frame.origin_minute.to_numpy()/1440
        week=np.eye(7)[frame.weekday.to_numpy()]
        node_lookup={node:i for i,node in enumerate(node_registry)};node_matrix=np.eye(51)[frame.node_id.map(node_lookup).to_numpy()]
        X=np.column_stack([(raw-mean)/scale,np.sin(clock),np.cos(clock),week,node_matrix])
        check(f'dense_feature_shape:H{H}',X.shape==(len(frame),65) and np.isfinite(X).all())
        y_train=target_train.current_speed_kmh.to_numpy();y_val=target_val.current_speed_kmh.to_numpy()
        val_frame=frame.loc[val_mask,['node_id','origin','target','H_h','partition','stratum']].copy()
        val_frame['reference_record_id']=reference_ids[val_mask].astype(int);val_frame['provider_reference_speed_kmh']=y_val
        candidates={};candidate_metrics=[]
        for alpha in ALPHAS:
            model=Ridge(alpha=alpha,fit_intercept=True,positive=False,solver='svd');model.fit(X[train_mask],y_train)
            pred=model.predict(X[val_mask]);check(f'validation_finite:H{H}:alpha{alpha}',np.isfinite(pred).all())
            measures=metric(pred,y_val);candidate_metrics.append(dict(H_h=H,alpha=alpha,N_train=len(y_train),N_validation=len(y_val),validation_mae_kmh=measures['mae_kmh'],validation_rmse_kmh=measures['rmse_kmh']))
            val_frame[f'prediction_alpha_{alpha:g}_kmh']=pred;candidates[alpha]=model
            for name,value in zip(names,model.coef_):coefficients.append(dict(H_h=H,alpha=alpha,parameter=name,value=float(value)))
            coefficients.append(dict(H_h=H,alpha=alpha,parameter='intercept',value=float(model.intercept_)))
        best=min(r['validation_mae_kmh'] for r in candidate_metrics)
        chosen=max(r['alpha'] for r in candidate_metrics if r['validation_mae_kmh']<=best+1e-12);model=candidates[chosen]
        for r in candidate_metrics:r['selected']=r['alpha']==chosen
        selection.extend(candidate_metrics)
        state=dict(H_h=H,alpha=chosen,feature_names=names,speed_mean_kmh=mean.tolist(),speed_population_sd_kmh=sd.tolist(),speed_scale=scale.tolist(),constant_speed_features=[ROLES[i] for i in range(5) if sd[i]==0],coefficients=model.coef_.tolist(),intercept=float(model.intercept_),N_train=int(train_mask.sum()),N_validation=int(val_mask.sum()),fit_partition='train only',selected_with='common validation MAE',validation_refit=False,ridge_parameters=model.get_params(),training_design_sha256=hashlib.sha256(X[train_mask].astype('<f8').tobytes(order='C')).hexdigest(),training_target_sha256=hashlib.sha256(y_train.astype('<f8').tobytes(order='C')).hexdigest())
        dump(OUT/f'models/RIDGE_H{H}.json',state)
        training_records.append(dict(H_h=H,N_train=int(train_mask.sum()),N_validation=int(val_mask.sum()),issuable_train=int((frame.partition=='train').sum()),alpha=chosen,feature_count=65,constant_speed_columns=int((sd==0).sum()),training_design_sha256=state['training_design_sha256'],training_target_sha256=state['training_target_sha256']))
        write(OUT/f'validation/H{H}_ALPHA_PREDICTIONS.csv',val_frame)
        featurecols=['node_id','origin','target','H_h','partition','stratum','origin_minute','weekday']+sum(([role+'_record_id',role+'_speed_kmh',role+'_capture'] for role in ROLES),[])
        write(OUT/f'features/H{H}_VISIBLE_FEATURES.csv',frame[featurecols])
        issued=frame[['node_id','origin','target','H_h','partition','stratum']].copy()
        issued['Persistence_prediction_kmh']=raw[:,0];issued['Seasonal24_prediction_kmh']=raw[:,4];issued['Ridge_prediction_kmh']=model.predict(X)
        for method in METHODS:
            check(f'all_issued_predictions_finite:H{H}:{method}',np.isfinite(issued[method+'_prediction_kmh']).all())
            issued[method+'_status']='SUCCESS'
        # This payload contains no future speed or reference-existence flag.
        write(OUT/f'predictions/H{H}_ISSUED_PREDICTIONS.csv',issued)
        # Future-reference attachment takes place only after issuance is saved.
        scored=issued.copy();scored['reference_record_id']=pd.Series(reference_ids).astype('Int64')
        scored['reference_status']=np.where(np.isfinite(reference_ids),'VALID_REFERENCE','NO_VALID_SCORING_REFERENCE')
        scored['provider_reference_speed_kmh']=scored.reference_record_id.map(source_speed)
        for field in ['capture_time_local','source_file','source_row_number']:
            scored['reference_'+field]=scored.reference_record_id.map(observations[field].to_dict())
        for method in METHODS:
            scored[method+'_error_kmh']=scored[method+'_prediction_kmh']-scored.provider_reference_speed_kmh
            check(f'unscored_not_zero_error:H{H}:{method}',scored.loc[scored.reference_status!='VALID_REFERENCE',method+'_error_kmh'].isna().all())
        write(OUT/f'predictions/H{H}_REFERENCE_ATTACHED.csv',scored)
        test=scored[(scored.partition=='test')&(scored.reference_status=='VALID_REFERENCE')].copy()
        check(f'test_support:H{H}',len(test)==int(support.loc[(support.H_h==H)&(support.partition=='test'),'scorable'].iloc[0]))
        for part in PARTS:
            part_frame=scored[scored.partition==part];valid=part_frame.reference_status=='VALID_REFERENCE'
            supp=support[(support.H_h==H)&(support.partition==part)].iloc[0]
            for method in METHODS:
                completion.append(dict(H_h=H,partition=part,method=method,candidate_decisions=int(supp.candidate_decisions),same_partition_candidates=int(supp.same_partition_candidates),input_ready=int(supp.input_ready),predictions_issued=len(part_frame),successful_predictions=int((part_frame[method+'_status']=='SUCCESS').sum()),failed_predictions=int((part_frame[method+'_status']!='SUCCESS').sum()),valid_scoring_references=int(valid.sum()),unscored_predictions=int((~valid).sum()),common_successful_scores=int(valid.sum()),method_completion_fraction=1.0,common_retention_fraction=1.0,scored_fraction_of_issued=float(valid.mean())))
        all_test.append(test)
        print(f'H={H}: selected alpha={chosen:g}, train={len(y_train)}, validation={len(y_val)}, test={len(test)}',flush=True)
    write(OUT/'models/ALPHA_VALIDATION_METRICS.csv',selection);write(OUT/'models/ALL_ALPHA_COEFFICIENTS.csv',coefficients);write(OUT/'models/TRAINING_RECORDS.csv',training_records)
    write(OUT/'results/COMPLETION_COUNTS.csv',completion)
    test=pd.concat(all_test,ignore_index=True);test['target_date']=test.target.dt.strftime('%Y-%m-%d')
    overall=[];node_metrics=[];date_metrics=[];layer_date_metrics=[];paired=[];paired_summary=[];long_scores=[]
    for H in [1,3,6]:
        ht=test[test.H_h==H]
        for level in LEVELS:
            subset=ht if level=='Overall' else ht[ht.stratum==level]
            sup=(support if level=='Overall' else layer_support)
            filt=(sup.H_h==H)&(sup.partition=='test')
            if level!='Overall':filt&=sup.stratum==level
            s=sup[filt].iloc[0]
            for method in METHODS:
                measures=metric(subset[method+'_prediction_kmh'],subset.provider_reference_speed_kmh)
                overall.append(dict(H_h=H,stratum=level,method=method,N_scores=len(subset),mae_kmh=measures['mae_kmh'],rmse_kmh=measures['rmse_kmh'],assigned_node_count=51 if level=='Overall' else int((availability.stratum==level).sum()),scoring_node_count=subset.node_id.nunique(),target_date_count=subset.target_date.nunique(),candidate_decisions=int(s.candidate_decisions),same_partition_candidates=int(s.same_partition_candidates),input_ready=int(s.input_ready),common_retention_fraction=1.0,score_fraction_of_input_ready=len(subset)/int(s.input_ready)))
        for (node,level),group in ht.groupby(['node_id','stratum']):
            for method in METHODS:node_metrics.append(dict(H_h=H,node_id=node,stratum=level,method=method,**metric(group[method+'_prediction_kmh'],group.provider_reference_speed_kmh)))
        for date,group in ht.groupby('target_date'):
            for method in METHODS:date_metrics.append(dict(H_h=H,target_date=date,method=method,node_count=group.node_id.nunique(),**metric(group[method+'_prediction_kmh'],group.provider_reference_speed_kmh)))
        for (date,level),group in ht.groupby(['target_date','stratum']):
            for method in METHODS:layer_date_metrics.append(dict(H_h=H,target_date=date,stratum=level,method=method,node_count=group.node_id.nunique(),**metric(group[method+'_prediction_kmh'],group.provider_reference_speed_kmh)))
        for first,second in [('Ridge','Persistence'),('Ridge','Seasonal24'),('Persistence','Seasonal24')]:
            dif=ht[['node_id','origin','target','H_h','stratum','target_date']].copy();dif['first_method']=first;dif['second_method']=second
            e1=ht[first+'_error_kmh'].to_numpy();e2=ht[second+'_error_kmh'].to_numpy();dif['absolute_error_difference_kmh']=np.abs(e1)-np.abs(e2);dif['squared_error_difference_kmh2']=e1**2-e2**2
            paired.append(dif)
            for level in LEVELS:
                d=dif if level=='Overall' else dif[dif.stratum==level]
                paired_summary.append(dict(H_h=H,stratum=level,first_method=first,second_method=second,N=len(d),mean_absolute_error_difference_kmh=math.fsum(d.absolute_error_difference_kmh)/len(d),mean_squared_error_difference_kmh2=math.fsum(d.squared_error_difference_kmh2)/len(d),interpretation='negative favors first method; descriptive paired difference, no significance test'))
        for method in METHODS:
            scores=ht[['node_id','origin','target','H_h','stratum','target_date','reference_record_id','provider_reference_speed_kmh','reference_capture_time_local','reference_source_file','reference_source_row_number']].copy()
            scores['method']=method;scores['prediction_kmh']=ht[method+'_prediction_kmh'];scores['error_kmh']=ht[method+'_error_kmh'];scores['status']='SUCCESS';long_scores.append(scores)
    write(OUT/'results/METRICS_OVERALL_AND_STRATA.csv',overall);write(OUT/'results/METRICS_BY_NODE.csv',node_metrics);write(OUT/'results/METRICS_BY_TARGET_DATE.csv',date_metrics);write(OUT/'results/METRICS_BY_TARGET_DATE_STRATUM.csv',layer_date_metrics);write(OUT/'results/PAIRED_POINT_ERROR_DIFFERENCES.csv',pd.concat(paired,ignore_index=True));write(OUT/'results/PAIRED_MEAN_ERROR_DIFFERENCES.csv',paired_summary);write(OUT/'results/TEST_POINT_SCORES.csv',pd.concat(long_scores,ignore_index=True))
    nm=pd.DataFrame(node_metrics);macro=[];ratios=[];mm={(r['H_h'],r['stratum'],r['method']):r for r in overall}
    for H in [1,3,6]:
        for method in METHODS:
            for level in LEVELS:
                group=nm[(nm.H_h==H)&(nm.method==method)]
                if level!='Overall':group=group[group.stratum==level]
                macro.append(dict(H_h=H,stratum=level,method=method,scoring_node_count=len(group),node_macro_mae_kmh=math.fsum(group.mae_kmh)/len(group)))
            high=mm[(H,'High',method)]['mae_kmh']
            for numerator in ['Medium','Low']:
                top=mm[(H,numerator,method)]['mae_kmh'];ratios.append(dict(H_h=H,method=method,numerator_stratum=numerator,denominator_stratum='High',numerator_mae_kmh=top,denominator_mae_kmh=high,mae_ratio=top/high if high>0 else None,status='ESTIMABLE' if high>0 else 'HIGH_MAE_ZERO'))
    write(OUT/'results/NODE_MACRO_MAE.csv',macro);write(OUT/'results/STRATUM_MAE_RATIOS.csv',ratios)
    intersection=pd.read_csv(B06/'TEST_COMMON_ORIGINS_ALL_H.csv',parse_dates=['origin']);shared=key_index(intersection)
    common=[]
    for H in [1,3,6]:
        subset=test[(test.H_h==H)&key_index(test).isin(shared)]
        check(f'common_origins:H{H}',len(subset)==2504 and set(key_index(subset))==set(shared))
        for method in METHODS:common.append(dict(H_h=H,method=method,node_count=subset.node_id.nunique(),target_date_count=subset.target_date.nunique(),**metric(subset[method+'_prediction_kmh'],subset.provider_reference_speed_kmh)))
    write(OUT/'results/COMMON_ORIGIN_ALL_H_METRICS.csv',common)
    for r in LOCK:
        r['sha256_after']=sha(Path(r['path']));r['unchanged']=r['sha256_after']==r['sha256_before'];check('unchanged:'+Path(r['path']).name,r['unchanged'])
    write(OUT/'INPUT_LOCK.csv',LOCK);write(OUT/'qa/BUILD_QA_CHECKS.csv',QA)
    dump(OUT/'RUN_CONTEXT.json',dict(started_at_utc=start,finished_at_utc=datetime.now(timezone.utc).isoformat(),run_id=OUT.parent.name,python=sys.version,executable=sys.executable,platform=platform.platform(),numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,sklearn=sklearn.__version__,script_sha256=sha(Path(__file__)),blas_thread_limits={k:os.environ[k] for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']},candidate_models_fitted=15,selected_models=3,training_plus_validation_refits=0,test_model_updates=0,plots_generated=0,QA_count=len(QA),failed_count=0))
    print(json.dumps({'QA_count':len(QA),'overall':[r for r in overall if r['stratum']=='Overall'],'selected_alphas':[r for r in selection if r['selected']]},ensure_ascii=True,indent=2),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        dump(OUT/'FAILED_RUN.json',dict(time_utc=datetime.now(timezone.utc).isoformat(),error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),status='FAILED; do not treat partial outputs as validated results'))
        raise
