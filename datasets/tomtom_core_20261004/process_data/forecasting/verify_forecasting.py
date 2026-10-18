"""Independent input/provenance and numerical verification using ridge normal equations.
Does not import sklearn, refit a published model, change the protocol, or draw a figure.
"""
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timezone
import csv,hashlib,json,math,os,sys,traceback
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
B06=ROOT/'outputs/Manuscript_Execution_20261007_b06_001243Z/figure7a_review_forecast_admission'
TRAFFIC=ROOT/'outputs/TomTom_Core_Freeze_20261004/tomtom_15min_frozen_2025-12-08_2025-12-31.csv'
METHODS=['Persistence','Seasonal24','Ridge'];ROLES=['lag1','lag2','lag3','lag4','seasonal'];LEVELS=['Overall','Low','Medium','High'];QA=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def frame(p,**kw):return pd.read_csv(p,float_precision='round_trip',**kw)
def records(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def check(name,ok,detail=''):
    QA.append(dict(check=name,status='PASS' if bool(ok) else 'FAIL',detail=str(detail)))
    if not ok:raise AssertionError(name+': '+str(detail))
def close(name,a,b,tol=1e-10):check(name,abs(float(a)-float(b))<=tol,dict(actual=float(a),expected=float(b),tolerance=tol))
def metrics(e):return math.fsum(float(abs(x)) for x in e)/len(e),math.sqrt(math.fsum(float(x*x) for x in e)/len(e))
def keys(f):return pd.MultiIndex.from_frame(f[['node_id','origin']])

def main():
    if (OUT/'qa/INDEPENDENT_QA.json').exists():raise RuntimeError('Refusing to overwrite independent verification')
    cfg=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    data=frame(TRAFFIC,usecols=['node_id','interval_timestamp_local','capture_time_local','current_speed_kmh','raw_observed_flag','imputed_flag','source_file','source_row_number'],parse_dates=['interval_timestamp_local','capture_time_local']);data.index=np.arange(1,len(data)+1)
    original=data.copy();original.index.name='frozen_record_id';nodes=sorted(data.node_id.unique());lookup=data.set_index(['node_id','interval_timestamp_local'])
    alpha_metrics=frame(OUT/'models/ALPHA_VALIDATION_METRICS.csv');coeff=frame(OUT/'models/ALL_ALPHA_COEFFICIENTS.csv')
    check('fixed_feature_contract',len(cfg['ridge_features'])==65 and cfg['ridge_features']==[role+'_speed_kmh' for role in ROLES]+['origin_clock_sin','origin_clock_cos']+['weekday_'+str(i) for i in range(7)]+['node_'+node for node in nodes] and not cfg['refit_train_plus_validation'] and not cfg['prediction_clipping'] and not cfg['confidence_intervals'])
    check('all_raw_original_nonimputed',(data.raw_observed_flag=='YES').all() and (data.imputed_flag=='NO').all())
    rebuilt_test=[];completion=frame(OUT/'results/COMPLETION_COUNTS.csv')
    for H in [1,3,6]:
        print(f'Independent H={H}: checking every input and issued prediction',flush=True)
        features=frame(OUT/f'features/H{H}_VISIBLE_FEATURES.csv',parse_dates=['origin','target']+[role+'_capture' for role in ROLES])
        expected_inputs=frame(B06/f'samples/H{H}_ISSUABLE_KEYS.csv',parse_dates=['origin','target'])
        issued=frame(OUT/f'predictions/H{H}_ISSUED_PREDICTIONS.csv',parse_dates=['origin','target'])
        attached=frame(OUT/f'predictions/H{H}_REFERENCE_ATTACHED.csv',parse_dates=['origin','target','reference_capture_time_local'])
        check(f'issuance_key_order_H{H}',len(features)==len(expected_inputs)==len(issued)==len(attached) and list(keys(features))==list(keys(expected_inputs))==list(keys(issued))==list(keys(attached)) and not issued.duplicated(['node_id','origin']).any())
        check(f'issued_payload_without_reference_H{H}',not any('reference' in c or c.endswith('_error_kmh') for c in issued.columns))
        for role in ROLES:
            ids=features[role+'_record_id'].to_numpy(dtype=int);source=original.loc[ids].reset_index(drop=True)
            offset=-15*(ROLES.index(role)+1) if role!='seasonal' else 60*H-1440
            check(f'every_input_value_H{H}:{role}',np.array_equal(source.current_speed_kmh.to_numpy(),features[role+'_speed_kmh'].to_numpy()) and np.array_equal(ids,expected_inputs[role+'_record_id'].to_numpy()))
            check(f'every_input_time_H{H}:{role}',np.array_equal(source.node_id.to_numpy(),features.node_id.to_numpy()) and np.array_equal(source.interval_timestamp_local.to_numpy(),(features.origin+pd.Timedelta(minutes=offset)).to_numpy()) and np.array_equal(source.capture_time_local.to_numpy(),features[role+'_capture'].to_numpy()) and (source.capture_time_local.to_numpy()<=features.origin.to_numpy()).all())
        check(f'calendar_target_key_H{H}',np.array_equal(features.target.to_numpy(),(features.origin+pd.Timedelta(hours=H)).to_numpy()) and np.array_equal(features.origin_minute.to_numpy(),(features.origin.dt.hour*60+features.origin.dt.minute).to_numpy()) and np.array_equal(features.weekday.to_numpy(),features.origin.dt.weekday.to_numpy()))
        score_keys=frame(B06/f'samples/H{H}_SCORABLE_KEYS.csv',parse_dates=['origin','target']).set_index(['node_id','origin'])
        ref_ids=score_keys.reference_record_id.reindex(keys(features)).to_numpy()
        has_reference=np.isfinite(ref_ids);tmask=(features.partition=='train').to_numpy()&has_reference;vmask=(features.partition=='validation').to_numpy()&has_reference
        check(f'reference_existence_preserved_H{H}',np.array_equal(attached.reference_record_id.notna().to_numpy(),has_reference) and np.array_equal(attached.loc[has_reference,'reference_record_id'].to_numpy(dtype=int),ref_ids[has_reference].astype(int)))
        ytrain=original.loc[ref_ids[tmask].astype(int),'current_speed_kmh'].to_numpy();yv=original.loc[ref_ids[vmask].astype(int),'current_speed_kmh'].to_numpy()
        model=json.loads((OUT/f'models/RIDGE_H{H}.json').read_text(encoding='utf-8'))
        raw=features[[role+'_speed_kmh' for role in ROLES]].to_numpy();train_raw=raw[tmask]
        mean=np.array([math.fsum(col)/len(col) for col in train_raw.T]);sd=np.array([math.sqrt(math.fsum(float((x-m)**2) for x in col)/len(col)) for col,m in zip(train_raw.T,mean)]);scale=np.where(sd==0,1.,sd)
        check(f'train_only_scaler_H{H}',np.max(np.abs(mean-np.array(model['speed_mean_kmh'])))<1e-10 and np.max(np.abs(sd-np.array(model['speed_population_sd_kmh'])))<1e-10 and np.max(np.abs(scale-np.array(model['speed_scale'])))<1e-10 and int(tmask.sum())==model['N_train'] and int(vmask.sum())==model['N_validation'] and model['fit_partition']=='train only' and not model['validation_refit'])
        clock=features.origin_minute.to_numpy()*(2*np.pi/1440)
        weekdays=(features.weekday.to_numpy()[:,None]==np.arange(7)[None,:]).astype(float)
        node_codes=(features.node_id.to_numpy()[:,None]==np.array(nodes)[None,:]).astype(float)
        X=np.column_stack([(raw-mean)/scale,np.sin(clock),np.cos(clock),weekdays,node_codes]);Xt=X[tmask];xbar=Xt.mean(axis=0);ybar=float(ytrain.mean());Xc=Xt-xbar;yc=ytrain-ybar
        gram=Xc.T@Xc;rhs=Xc.T@yc
        validation=frame(OUT/f'validation/H{H}_ALPHA_PREDICTIONS.csv',parse_dates=['origin','target'])
        check(f'validation_same_keys_H{H}',list(keys(validation))==list(keys(features.loc[vmask])) and np.array_equal(validation.provider_reference_speed_kmh.to_numpy(),yv))
        for alpha in cfg['alpha_candidates']:
            independent_coef=np.linalg.solve(gram+float(alpha)*np.eye(65),rhs);independent_intercept=ybar-float(xbar@independent_coef)
            saved=coeff[(coeff.H_h==H)&(coeff.alpha==alpha)].set_index('parameter').value
            savedcoef=np.array([saved[name] for name in cfg['ridge_features']]);savedintercept=float(saved['intercept'])
            check(f'normal_equations_coefficients_H{H}:alpha{alpha}',np.max(np.abs(independent_coef-savedcoef))<1e-8 and abs(independent_intercept-savedintercept)<1e-8)
            vp=validation[f'prediction_alpha_{alpha:g}_kmh'].to_numpy();recomputed=X[vmask]@savedcoef+savedintercept
            check(f'validation_prediction_replay_H{H}:alpha{alpha}',np.max(np.abs(recomputed-vp))<1e-10 and np.max(np.abs((X[vmask]@independent_coef+independent_intercept)-vp))<1e-8)
            mae,rmse=metrics(vp-yv);r=alpha_metrics[(alpha_metrics.H_h==H)&(alpha_metrics.alpha==alpha)].iloc[0]
            close(f'validation_MAE_H{H}:alpha{alpha}',mae,r.validation_mae_kmh);close(f'validation_RMSE_H{H}:alpha{alpha}',rmse,r.validation_rmse_kmh)
            check(f'validation_training_support_H{H}:alpha{alpha}',int(r.N_train)==int(tmask.sum()) and int(r.N_validation)==int(vmask.sum()))
        hm=alpha_metrics[alpha_metrics.H_h==H];minimal=hm.validation_mae_kmh.min();chosen=hm.loc[hm.validation_mae_kmh<=minimal+1e-12,'alpha'].max()
        check(f'validation_only_alpha_choice_H{H}',float(chosen)==float(model['alpha']) and int(hm.selected.sum())==1 and bool(hm.loc[hm.alpha==chosen,'selected'].iloc[0]))
        check(f'selected_coefficients_from_training_H{H}',np.max(np.abs(np.array(model['coefficients'])-np.array([coeff[(coeff.H_h==H)&(coeff.alpha==chosen)&(coeff.parameter==name)].value.iloc[0] for name in cfg['ridge_features']])))<1e-14)
        expected_preds={'Persistence':raw[:,0],'Seasonal24':raw[:,4],'Ridge':X@np.array(model['coefficients'])+float(model['intercept'])}
        for method,pred in expected_preds.items():
            check(f'every_issued_prediction_H{H}:{method}',np.isfinite(pred).all() and np.max(np.abs(pred-issued[method+'_prediction_kmh'].to_numpy()))<1e-10 and (issued[method+'_status']=='SUCCESS').all() and np.array_equal(issued[method+'_prediction_kmh'].to_numpy(),attached[method+'_prediction_kmh'].to_numpy()))
            check(f'no_reference_no_error_H{H}:{method}',attached.loc[~has_reference,method+'_error_kmh'].isna().all() and attached.loc[~has_reference,'provider_reference_speed_kmh'].isna().all())
        reference=original.loc[ref_ids[has_reference].astype(int)].reset_index()
        f=features.loc[has_reference].reset_index(drop=True);a=attached.loc[has_reference].reset_index(drop=True)
        check(f'all_provider_reference_provenance_H{H}',np.array_equal(reference.node_id.to_numpy(),f.node_id.to_numpy()) and np.array_equal(reference.interval_timestamp_local.to_numpy(),f.target.to_numpy()) and (reference.capture_time_local.to_numpy()>f.origin.to_numpy()).all() and np.array_equal(reference.current_speed_kmh.to_numpy(),a.provider_reference_speed_kmh.to_numpy()) and np.array_equal(reference.source_file.to_numpy(),a.reference_source_file.to_numpy()) and np.array_equal(reference.source_row_number.to_numpy(),a.reference_source_row_number.to_numpy()) and np.array_equal(reference.capture_time_local.to_numpy(),a.reference_capture_time_local.to_numpy()))
        for partition in ['train','validation','test']:
            mask=(f.partition==partition).to_numpy();end=pd.Timestamp(cfg['partitions_left_closed_right_open'][partition][1]);start=pd.Timestamp(cfg['partitions_left_closed_right_open'][partition][0])
            check(f'split_and_label_cutoff_H{H}:{partition}',((f.loc[mask,'origin']>=start)&(f.loc[mask,'origin']<end)&(f.loc[mask,'target']>=start)&(f.loc[mask,'target']<end)).all() and (partition=='test' or (reference.loc[mask,'capture_time_local']<end).all()))
            p=attached[attached.partition==partition];nref=int(p.reference_record_id.notna().sum())
            for method in METHODS:
                r=completion[(completion.H_h==H)&(completion.partition==partition)&(completion.method==method)].iloc[0]
                check(f'completion_counts_H{H}:{partition}:{method}',int(r.input_ready)==int(r.predictions_issued)==int(r.successful_predictions)==len(p) and int(r.failed_predictions)==0 and int(r.valid_scoring_references)==int(r.common_successful_scores)==nref and int(r.unscored_predictions)==len(p)-nref and float(r.method_completion_fraction)==float(r.common_retention_fraction)==1 and abs(float(r.scored_fraction_of_issued)-nref/len(p))<1e-14)
        t=attached[(attached.partition=='test')&attached.reference_record_id.notna()].copy();t['target_date']=t.target.dt.strftime('%Y-%m-%d');rebuilt_test.append(t)
        for method in METHODS:check(f'all_attached_errors_H{H}:{method}',np.max(np.abs((a[method+'_prediction_kmh']-a.provider_reference_speed_kmh)-a[method+'_error_kmh']))<1e-10)
    test=pd.concat(rebuilt_test,ignore_index=True);test_index=test.set_index(['H_h','node_id','origin'])
    long=frame(OUT/'results/TEST_POINT_SCORES.csv',parse_dates=['origin','target','reference_capture_time_local'])
    check('test_long_unique_keys',len(long)==(5863+5727+5535)*3 and not long.duplicated(['H_h','node_id','origin','method']).any())
    for method in METHODS:
        s=long[long.method==method];original_order=test_index.reindex(pd.MultiIndex.from_frame(s[['H_h','node_id','origin']]))
        check('same_target_keys:'+method,set(pd.MultiIndex.from_frame(s[['H_h','node_id','origin']]))==set(test_index.index) and np.max(np.abs(s.prediction_kmh.to_numpy()-original_order[method+'_prediction_kmh'].to_numpy()))<1e-10 and np.array_equal(s.provider_reference_speed_kmh.to_numpy(),original_order.provider_reference_speed_kmh.to_numpy()) and np.max(np.abs(s.error_kmh.to_numpy()-(s.prediction_kmh-s.provider_reference_speed_kmh).to_numpy()))<1e-10)
    tables=[('METRICS_OVERALL_AND_STRATA.csv',['H_h','stratum','method'],'N_scores'),('METRICS_BY_NODE.csv',['H_h','node_id','stratum','method'],'N'),('METRICS_BY_TARGET_DATE.csv',['H_h','target_date','method'],'N'),('METRICS_BY_TARGET_DATE_STRATUM.csv',['H_h','target_date','stratum','method'],'N')]
    for filename,groupcols,nfield in tables:
        for r in records(OUT/'results'/filename):
            s=long[long.H_h==int(r['H_h'])]
            for field in groupcols[1:]:
                if field=='stratum' and r[field]=='Overall':continue
                s=s[s[field]==r[field]]
            mae,rmse=metrics(s.error_kmh.to_numpy());tag=':'.join(r[f] for f in groupcols)
            check(filename+':'+tag,len(s)==int(r[nfield]) and abs(mae-float(r['mae_kmh']))<1e-10 and abs(rmse-float(r['rmse_kmh']))<1e-10)
    overall=frame(OUT/'results/METRICS_OVERALL_AND_STRATA.csv');nm=frame(OUT/'results/METRICS_BY_NODE.csv')
    for r in records(OUT/'results/NODE_MACRO_MAE.csv'):
        n=nm[(nm.H_h==int(r['H_h']))&(nm.method==r['method'])]
        if r['stratum']!='Overall':n=n[n.stratum==r['stratum']]
        check('node_macro:'+str((r['H_h'],r['stratum'],r['method'])),len(n)==int(r['scoring_node_count']) and abs(math.fsum(n.mae_kmh)/len(n)-float(r['node_macro_mae_kmh']))<1e-10)
    for r in records(OUT/'results/STRATUM_MAE_RATIOS.csv'):
        n=overall[(overall.H_h==int(r['H_h']))&(overall.method==r['method'])]
        top=float(n.loc[n.stratum==r['numerator_stratum'],'mae_kmh'].iloc[0]);bottom=float(n.loc[n.stratum=='High','mae_kmh'].iloc[0])
        check('stratum_ratio:'+str((r['H_h'],r['method'],r['numerator_stratum'])),r['status']=='ESTIMABLE' and bottom>0 and abs(top-float(r['numerator_mae_kmh']))<1e-10 and abs(bottom-float(r['denominator_mae_kmh']))<1e-10 and abs(top/bottom-float(r['mae_ratio']))<1e-10)
    common=frame(OUT/'inputs/TEST_COMMON_ORIGINS_ALL_H.csv',parse_dates=['origin']);common_keys=keys(common)
    for r in records(OUT/'results/COMMON_ORIGIN_ALL_H_METRICS.csv'):
        s=long[(long.H_h==int(r['H_h']))&(long.method==r['method'])];s=s[keys(s).isin(common_keys)];mae,rmse=metrics(s.error_kmh.to_numpy())
        check('common_origin:'+str((r['H_h'],r['method'])),len(s)==int(r['N'])==2504 and set(keys(s))==set(common_keys) and abs(mae-float(r['mae_kmh']))<1e-10 and abs(rmse-float(r['rmse_kmh']))<1e-10)
    paired=frame(OUT/'results/PAIRED_POINT_ERROR_DIFFERENCES.csv',parse_dates=['origin','target'])
    for H in [1,3,6]:
        t=test[test.H_h==H].set_index(['node_id','origin'])
        for first,second in [('Ridge','Persistence'),('Ridge','Seasonal24'),('Persistence','Seasonal24')]:
            p=paired[(paired.H_h==H)&(paired.first_method==first)&(paired.second_method==second)];t0=t.reindex(keys(p));e1=t0[first+'_error_kmh'].to_numpy();e2=t0[second+'_error_kmh'].to_numpy()
            check(f'paired_point_errors_H{H}:{first}:{second}',len(p)==len(t) and set(keys(p))==set(t.index) and np.max(np.abs(p.absolute_error_difference_kmh.to_numpy()-(np.abs(e1)-np.abs(e2))))<1e-10 and np.max(np.abs(p.squared_error_difference_kmh2.to_numpy()-(e1**2-e2**2)))<1e-9)
    for r in records(OUT/'results/PAIRED_MEAN_ERROR_DIFFERENCES.csv'):
        p=paired[(paired.H_h==int(r['H_h']))&(paired.first_method==r['first_method'])&(paired.second_method==r['second_method'])]
        if r['stratum']!='Overall':p=p[p.stratum==r['stratum']]
        check('paired_summary:'+str((r['H_h'],r['stratum'],r['first_method'],r['second_method'])),len(p)==int(r['N']) and abs(math.fsum(p.absolute_error_difference_kmh)/len(p)-float(r['mean_absolute_error_difference_kmh']))<1e-10 and abs(math.fsum(p.squared_error_difference_kmh2)/len(p)-float(r['mean_squared_error_difference_kmh2']))<1e-9)
    for r in records(OUT/'INPUT_LOCK.csv'):check('independent_input_hash:'+Path(r['path']).name,sha(Path(r['path']))==r['sha256_before']==r['sha256_after'])
    pd.DataFrame(QA).to_csv(OUT/'qa/INDEPENDENT_QA_CHECKS.csv',index=False,encoding='utf-8-sig')
    dump(OUT/'qa/INDEPENDENT_QA.json',dict(check_count=len(QA),failed_count=0,verified_test_rows=51375,implementation='independent original-key feature/provenance replay, normal-equation coefficient comparison to sklearn SVD, all issued prediction replay and all published metric groups',normal_equations_tolerance=1e-8,prediction_and_metric_replay_tolerance=1e-10,python=sys.version,executable=sys.executable,numpy=np.__version__,pandas=pd.__version__,sklearn_imported=False,script_sha256=sha(Path(__file__)),finished_at_utc=datetime.now(timezone.utc).isoformat()))
    print(json.dumps({'independent_QA_count':len(QA),'failed_count':0,'verified_test_rows':51375},indent=2),flush=True)

if __name__=='__main__':
    try:main()
    except Exception as exc:
        dump(OUT/'qa/FAILED_VERIFICATION.json',dict(error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc(),status='FAILED; do not accept the batch until repaired and reverified'))
        raise
