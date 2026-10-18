"""Review the received raster and freeze forecast-admission metadata. No plotting or fitting."""
from pathlib import Path
from datetime import datetime, timezone
import csv, hashlib, importlib.util, json, math, platform, shutil, sys
import numpy as np
import pandas as pd
from PIL import Image

ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
FREEZE=ROOT/'outputs/TomTom_Core_Freeze_20261004'
B01=ROOT/'outputs/Manuscript_Execution_20261006_b01_054939Z/batch01_preflight'
B03=ROOT/'outputs/Manuscript_Execution_20261006_b03_124252Z/batch03_reconstruction'
HANDOFF=ROOT/'outputs/Manuscript_Preparation_20261006/论文写作交接与结果证据清单.md'
FIGURE=Path(r'D:\山田夫人\论文\论文 - 1\图\2026_10_5 图\Figure7a_600dpi.png')
OUT=Path(__file__).resolve().parent
TRAFFIC=FREEZE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv'
FORMAT='%Y-%m-%d %H:%M:%S'
PARTS={'train':('2025-12-08','2025-12-24'),'validation':('2025-12-24','2025-12-28'),'test':('2025-12-28','2026-01-01')}
METHODS=['Linear','LOCF','Train-TOD median','Spatial median']
QA=[];LOCK=[]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def check(name,ok,detail=''):
    QA.append({'check':name,'status':'PASS' if bool(ok) else 'FAIL','detail':str(detail)})
    if not ok:raise AssertionError(name+': '+str(detail))
def write(p,x):pd.DataFrame(x).to_csv(p,index=False,encoding='utf-8-sig',float_format='%.17g',date_format=FORMAT)
def lock(p,expected='',role=''):
    actual=sha(p)
    if expected:check('hash:'+p.name,actual==expected)
    LOCK.append(dict(path=str(p),role=role,expected_sha256=expected,sha256_before=actual,bytes=p.stat().st_size))

def review_figure():
    metrics=rows(B03/'results/METRICS_BY_LENGTH_METHOD.csv')
    points=pd.read_csv(B03/'results/POINT_SCORES.csv')
    points['error']=points.reconstructed_speed_kmh-points.hidden_provider_speed_kmh
    labels={1:[3.55,4.25,3.98,17.48],4:[3.66,4.04,4.53,16.81],12:[4.81,5.89,4.88,17.73],24:[4.14,4.53,3.87,22.93]}
    check('figure_sample_counts',[int(next(r['N_gaps'] for r in metrics if int(r['K'])==k)) for k in labels]==[300,300,211,17])
    evidence=[]
    for r in metrics:
        k=int(r['K']);method=r['method'];e=points.loc[(points.K==k)&(points.method==method),'error'].to_numpy()
        actual=math.sqrt(math.fsum(float(x*x) for x in e)/len(e))
        check(f'recompute_RMSE:{k}:{method}',abs(actual-float(r['pooled_rmse_kmh']))<1e-10)
        label=labels[k][METHODS.index(method)]
        check(f'received_annotation:{k}:{method}',f'{actual:.2f}'==f'{label:.2f}')
        evidence.append(dict(K=k,duration_h=k/4,method=method,source_rmse_kmh=actual,received_label=label,N_gaps=int(r['N_gaps']),node_count=int(r['node_count']),annotation_check='PASS',basis='manual transcription from user raster; RMSE recalculated from point scores'))
    image=Image.open(FIGURE);arr=np.asarray(image);dpi=image.info.get('dpi')
    check('raster_size',image.size==(4252,2392))
    check('raster_dpi',dpi is not None and max(abs(x-600) for x in dpi)<.01)
    colors={'Linear':(0,114,178),'LOCF':(230,159,0),'Train-TOD median':(0,158,115),'Spatial median':(204,121,167)}
    centers=[];intarr=arr.astype(np.int16)
    for method,rgb in colors.items():
        mask=np.max(np.abs(intarr-np.array(rgb)),axis=2)<=3;mask[:500]=False
        xs=np.flatnonzero(mask.sum(axis=0)>0)
        runs=np.split(xs,np.flatnonzero(np.diff(xs)>1)+1);runs=[r for r in runs if len(r)>5]
        check('four_raster_markers:'+method,len(runs)==4)
        for k,run in zip(labels,runs):
            ys=np.where(mask[:,run])[0]
            center=(float(ys.min())+float(ys.max()))/2
            centers.append(dict(K=k,method=method,x_center_px=(float(run[0])+float(run[-1]))/2,y_center_px=center))
    source={(int(r['K']),r['method']):float(r['pooled_rmse_kmh']) for r in metrics}
    calibration=[r for r in centers if r['method']!='Train-TOD median']
    slope,intercept=np.polyfit([source[(r['K'],r['method'])] for r in calibration],[r['y_center_px'] for r in calibration],1)
    check('raster_vertical_scale',slope<0 and abs(float(slope)+50.16)<.5)
    for r in centers:
        r['source_rmse_kmh']=source[(r['K'],r['method'])]
        r['position_residual_px']=r['y_center_px']-(intercept+slope*r['source_rmse_kmh'])
        check(f'raster_position:{r["K"]}:{r["method"]}',abs(r['position_residual_px'])<6)
    write(OUT/'FIGURE7A_VALUE_CHECK.csv',evidence);write(OUT/'FIGURE7A_RASTER_CHECK.csv',centers)
    (OUT/'received_figure').mkdir();shutil.copy2(FIGURE,OUT/'received_figure/Figure7a_received_600dpi.png')
    dump(OUT/'FIGURE7A_REVIEW.json',{'status':'accepted_for_progress','size':image.size,'dpi':dpi,'image_sha256':sha(FIGURE),'manual_layout_review':'all 16 annotations, N=300/300/211/17, 17 gaps/15 nodes, axes, legend and panel label clear; no material overlaps or clipping observed','pixel_check_scope':'marker positions consistent with recomputed RMSE under inferred linear pixel calibration, tolerance 6 pixels; triangle geometry affects center; not an OCR or plotting-source audit','plotting_script_received':False,'other_formats_received':False})

def main():
    if (OUT/'CONFIG.json').exists():raise RuntimeError('Refusing to overwrite a completed or partial run')
    lock(FREEZE/'SHA256_MANIFEST.csv','b38f799858a7af711a81e217e66390d733ae53c53bc2367cf01c988271116111','frozen manifest')
    for r in rows(FREEZE/'SHA256_MANIFEST.csv'):lock(FREEZE/r['file'],r['sha256'],'frozen payload; byte identity')
    lock(HANDOFF,role='confirmed section 12 protocol')
    for name in ['SEMANTICS_AUDIT.md','BATCH01_ACCEPTANCE.md','TIME_FIELD_ANOMALIES.csv']:lock(B01/name,role='record-time evidence and its limits')
    prior={r['file']:r['sha256'] for r in rows(B03/'OUTPUT_MANIFEST.csv')}
    for name in ['results/METRICS_BY_LENGTH_METHOD.csv','results/POINT_SCORES.csv']:lock(B03/name,prior[name],'E06 figure reference')
    lock(FIGURE,role='user supplied completed figure; read only')
    review_figure()
    fields=['interval_timestamp_local','interval_timestamp_utc','timezone','node_id','current_speed_kmh','pd_create_time_local','capture_time_local','flow_create_time_local','source_file','source_row_number','raw_observed_flag','imputed_flag']
    data=pd.read_csv(TRAFFIC,usecols=fields,dtype={'node_id':str})
    data['frozen_record_id']=np.arange(1,len(data)+1)
    for field in ['interval_timestamp_local','pd_create_time_local','capture_time_local','flow_create_time_local']:data[field]=pd.to_datetime(data[field],format=FORMAT,errors='coerce')
    check('traffic_rows',len(data)==90929)
    check('all_four_times_parsed',not data[['interval_timestamp_local','pd_create_time_local','capture_time_local','flow_create_time_local']].isna().any().any())
    check('all_times_local_timezone',(data.timezone=='Asia/Kuching').all())
    utc=pd.to_datetime(data.interval_timestamp_utc,utc=True)
    check('UTC_matches_local_slot',(utc.dt.tz_convert('Asia/Kuching').dt.tz_localize(None)==data.interval_timestamp_local).all())
    check('unique_node_slot',not data.duplicated(['node_id','interval_timestamp_local']).any())
    check('original_finite_speed',(data.raw_observed_flag=='YES').all() and (data.imputed_flag=='NO').all() and np.isfinite(data.current_speed_kmh).all())
    check('slot_grid',((data.interval_timestamp_local.dt.minute%15==0)&(data.interval_timestamp_local.dt.second==0)).all())
    check('capture_at_or_after_slot',(data.capture_time_local>=data.interval_timestamp_local).all())
    late=data.capture_time_local>data.interval_timestamp_local+pd.Timedelta(minutes=15)
    check('late_anchor_records',int(late.sum())==9)
    check('prior_late_keys',set(zip(data.loc[late,'node_id'],data.loc[late,'source_row_number'].astype(str)))==set((r['node_id'],str(int(r['source_row_number']))) for r in rows(B01/'TIME_FIELD_ANOMALIES.csv') if r['anomaly']=='ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15') if 'anomaly' in rows(B01/'TIME_FIELD_ANOMALIES.csv')[0] else int(late.sum())==9)
    nodes=sorted(pd.read_csv(FREEZE/'tomtom_node_master_51.csv').node_id)
    check('fixed_node_registry',len(nodes)==51 and set(data.node_id)==set(nodes))
    train=data[(data.interval_timestamp_local>=pd.Timestamp(PARTS['train'][0]))&(data.interval_timestamp_local<pd.Timestamp(PARTS['train'][1]))]
    counts=train.groupby('node_id').size().reindex(nodes,fill_value=0)
    visible=train[train.capture_time_local<pd.Timestamp(PARTS['train'][1])].groupby('node_id').size().reindex(nodes,fill_value=0)
    avail=pd.DataFrame({'node_id':nodes,'expected_training_positions':1536,'existing_training_records':counts.to_numpy(),'cutoff_visible_records':visible.to_numpy()})
    avail['unknown_or_late_capture_records']=avail.existing_training_records-avail.cutoff_visible_records
    avail['availability']=avail.cutoff_visible_records/1536
    q1,q2=np.quantile(avail.availability,[1/3,2/3],method='linear')
    avail['stratum']=np.select([avail.availability<=q1,avail.availability<=q2],['Low','Medium'],default='High')
    check('training_denominator',1536==16*96 and int(counts.sum())==59009 and int(visible.sum())==59009)
    check('strata_nonoverlap',len(avail)==51 and avail.stratum.notna().all())
    write(OUT/'TRAINING_AVAILABILITY_STRATA.csv',avail)
    strata=avail.set_index('node_id').stratum.to_dict()
    config={'freeze_id':'TOMTOM_CORE_20261004','timezone':'Asia/Kuching','delta_minutes':15,'horizons_h':[1,3,6],'partitions_left_closed_right_open':PARTS,'target':'same-node provider speed snapshot at origin + H; not an hourly average','latest_anchor':'origin - 15 min; no fallback','input_slot_offsets_minutes':{'lag1':-15,'lag2':-30,'lag3':-45,'lag4':-60,'seasonal':'H*60 - 1440'},'input_capture_rule':'capture <= origin, exact slot, original finite non-imputed speed','reference_capture_rule':'capture > origin; train/validation capture < partition_end; test obtained after decision','candidate_grid':'all 51 nodes x all 2304 decision slots, independently for each H','issue_eligibility':'known calendar same-partition target and all five inputs visible; never conditional on future reference existence','scoring_eligibility':'issue eligibility then independently join valid future reference','training_availability_denominator':1536,'quantile_method':'linear on all 51 unrounded availability values','q1':float(q1),'q2':float(q2),'stratum_rule':'Low <= q1; Medium q1 < A <= q2; High > q2; ties not split','no_training_or_predictions':True,'no_plotting':True,'no_input_imputation':True,'no_target_or_weather_in_inputs':True,'model_selection_not_performed':True,'reference_is_ground_truth':False,'timestamp_semantics_status':'record-time proxy conditionally supported, actual online arrival unproved'}
    dump(OUT/'CONFIG.json',config)
    record_fields=['frozen_record_id','node_id','interval_timestamp_local','capture_time_local','pd_create_time_local','flow_create_time_local','timezone','source_file','source_row_number','raw_observed_flag','imputed_flag']
    write(OUT/'OBSERVATION_RECORD_INDEX.csv',data[record_fields])
    lookup=data.set_index(['node_id','interval_timestamp_local'])
    slots=pd.date_range('2025-12-08','2026-01-01',freq='15min',inclusive='left')
    base=pd.MultiIndex.from_product([nodes,slots],names=['node_id','origin']).to_frame(index=False)
    base['partition']=np.select([base.origin<pd.Timestamp('2025-12-24'),base.origin<pd.Timestamp('2025-12-28')],['train','validation'],default='test')
    base['partition_end']=base.partition.map({k:pd.Timestamp(v[1]) for k,v in PARTS.items()})
    base['stratum']=base.node_id.map(strata)
    check('candidate_full_grid',len(base)==117504)
    summary=[];layer_summary=[];exclusions=[];test_scores={};test_ready={}
    (OUT/'samples').mkdir()
    for H in [1,3,6]:
        audit=base.copy();audit['H_h']=H;audit['target']=audit.origin+pd.Timedelta(hours=H)
        audit['same_partition']=audit.target<audit.partition_end
        audit['input_primary_status']='OK'
        for role,offset in [('lag1',-15),('lag2',-30),('lag3',-45),('lag4',-60),('seasonal',60*H-1440)]:
            expected_slot=audit.origin+pd.Timedelta(minutes=offset)
            found=lookup.reindex(pd.MultiIndex.from_arrays([audit.node_id,expected_slot])).reset_index(drop=True)
            state=np.select([found.frozen_record_id.isna(),found.capture_time_local.isna(),found.capture_time_local>audit.origin],['MISSING','CAPTURE_UNKNOWN','NOT_YET_VISIBLE'],default='OK')
            audit[role+'_status']=state;audit[role+'_record_id']=found.frozen_record_id.astype('Int64')
            fail=(audit.input_primary_status=='OK')&(state!='OK');audit.loc[fail,'input_primary_status']=role+':'+pd.Series(state)[fail]
        audit['input_ready']=audit.same_partition&(audit.input_primary_status=='OK')
        # Save issuing eligibility BEFORE looking up any future reference.
        keycols=['node_id','origin','target','H_h','partition','stratum']
        inputfields=keycols+['same_partition','input_ready','input_primary_status']+sum(([role+'_status',role+'_record_id'] for role in ['lag1','lag2','lag3','lag4','seasonal']),[])
        write(OUT/f'samples/H{H}_INPUT_ADMISSION.csv',audit[inputfields])
        write(OUT/f'samples/H{H}_ISSUABLE_KEYS.csv',audit.loc[audit.input_ready,keycols+[role+'_record_id' for role in ['lag1','lag2','lag3','lag4','seasonal']]])
        target_lookup=lookup.reindex(pd.MultiIndex.from_arrays([audit.node_id,audit.target])).reset_index(drop=True)
        ref=np.select([target_lookup.frozen_record_id.isna(),target_lookup.capture_time_local.isna(),target_lookup.capture_time_local<=audit.origin,(audit.partition!='test')&(target_lookup.capture_time_local>=audit.partition_end)],['MISSING_REFERENCE','CAPTURE_UNKNOWN','REFERENCE_NOT_FUTURE','REFERENCE_AFTER_PARTITION_CUTOFF'],default='OK')
        audit['reference_status']=ref;audit['reference_record_id']=target_lookup.frozen_record_id.astype('Int64')
        audit['scorable']=audit.input_ready&(audit.reference_status=='OK')
        write(OUT/f'samples/H{H}_REFERENCE_AUDIT.csv',audit[keycols+['same_partition','reference_status','reference_record_id']])
        write(OUT/f'samples/H{H}_SCORABLE_KEYS.csv',audit.loc[audit.scorable,keycols+['reference_record_id']])
        for partition in PARTS:
            a=audit[audit.partition==partition];ready=a[a.input_ready];score=a[a.scorable]
            s=dict(H_h=H,partition=partition,candidate_decisions=len(a),cross_partition_targets=int((~a.same_partition).sum()),same_partition_candidates=int(a.same_partition.sum()),all_five_inputs_visible=int((a.input_primary_status=='OK').sum()),input_ready=len(ready),input_not_ready_within_partition=int((a.same_partition&~a.input_ready).sum()),ready_without_valid_reference=len(ready)-len(score),scorable=len(score),scorable_node_count=score.node_id.nunique(),target_date_count=score.target.dt.date.nunique(),input_ready_fraction_of_candidates=len(ready)/len(a),score_fraction_of_ready=len(score)/len(ready) if len(ready) else None)
            summary.append(s)
            primary=np.where(~a.same_partition,'TARGET_CROSSES_PARTITION',a.input_primary_status)
            for reason,count in pd.Series(primary).value_counts().items():exclusions.append(dict(H_h=H,partition=partition,stage='candidate_to_input_ready',reason=reason,count=int(count),overlap='mutually exclusive; calendar first, then first failing input in lag1/2/3/4/seasonal order'))
            for reason,count in ready.reference_status.value_counts().items():exclusions.append(dict(H_h=H,partition=partition,stage='input_ready_to_scorable',reason=reason,count=int(count),overlap='mutually exclusive reference status; OK denotes scorable'))
            check(f'count_reconciliation:{partition}:H{H}',s['candidate_decisions']==s['cross_partition_targets']+s['input_not_ready_within_partition']+s['input_ready'] and s['input_ready']==s['scorable']+s['ready_without_valid_reference'])
            check(f'nonempty_fit_support:{partition}:H{H}',len(score)>0)
            for layer in ['Low','Medium','High']:
                l=a[a.stratum==layer];sc=l[l.scorable]
                layer_summary.append(dict(H_h=H,partition=partition,stratum=layer,assigned_node_count=int((avail.stratum==layer).sum()),candidate_decisions=len(l),same_partition_candidates=int(l.same_partition.sum()),input_ready=int(l.input_ready.sum()),scorable=len(sc),scoring_node_count=sc.node_id.nunique(),target_date_count=sc.target.dt.date.nunique()))
        ts=audit[(audit.partition=='test')&audit.scorable]
        ti=audit[(audit.partition=='test')&audit.input_ready]
        test_scores[H]=set(zip(ts.node_id,ts.origin));test_ready[H]=set(zip(ti.node_id,ti.origin))
    write(OUT/'SAMPLE_SUPPORT_SUMMARY.csv',summary);write(OUT/'STRATIFIED_SUPPORT_SUMMARY.csv',layer_summary);write(OUT/'EXCLUSION_COUNTS.csv',exclusions)
    shared_scores=set.intersection(*test_scores.values());shared_inputs=set.intersection(*test_ready.values())
    write(OUT/'TEST_COMMON_ORIGINS_ALL_H.csv',[dict(node_id=node,origin=origin,stratum=strata[node]) for node,origin in sorted(shared_scores)])
    dump(OUT/'ADMISSION_SUMMARY.json',{'sample_support':summary,'q1':float(q1),'q2':float(q2),'stratum_node_counts':{k:int((avail.stratum==k).sum()) for k in ['Low','Medium','High']},'test_common_input_origins_all_H':len(shared_inputs),'test_common_scorable_origins_all_H':len(shared_scores),'models_fitted':0,'predictions_issued':0,'performance_metrics_computed':0,'record_time_gate':'PARTIAL; finite retrospective proxy supported, actual online arrival not established','sample_implementation_gate':'PASS subject to independent verification','library_check':{'sklearn_available':importlib.util.find_spec('sklearn') is not None,'numpy_version':np.__version__,'pandas_version':pd.__version__}})
    for r in LOCK:
        r['sha256_after']=sha(Path(r['path']));r['unchanged']=r['sha256_after']==r['sha256_before'];check('input_unchanged:'+Path(r['path']).name,r['unchanged'])
    write(OUT/'INPUT_LOCK.csv',LOCK);write(OUT/'QA_CHECKS.csv',QA)
    dump(OUT/'RUN_CONTEXT.json',{'run_id':OUT.parent.name,'started_at_utc':datetime.now(timezone.utc).isoformat(),'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'numpy':np.__version__,'pandas':pd.__version__,'script_sha256':sha(Path(__file__)),'scope':'figure review and full deterministic forecast-input/reference admission metadata only','no_images_generated_or_modified':True,'training_performed':False,'manual_visual_review':'original attached raster reviewed; text and labels clear','QA_count':len(QA),'failed_count':sum(x['status']=='FAIL' for x in QA)})
    print(json.dumps({'QA_count':len(QA),'failed_count':0,'summary':summary,'q1':float(q1),'q2':float(q2),'nodes_by_stratum':{k:int((avail.stratum==k).sum()) for k in ['Low','Medium','High']},'test_intersection':len(shared_scores)},ensure_ascii=True,indent=2))

if __name__=='__main__':main()
