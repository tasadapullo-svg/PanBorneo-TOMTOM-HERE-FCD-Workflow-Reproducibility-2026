"""Independently verify every decision using exact-key dictionaries, then package metadata."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
import csv,hashlib,json,math,sys,zipfile

OUT=Path(__file__).resolve().parent
ROOT=Path(r'D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1')
CORE=ROOT/'outputs/TomTom_Core_Freeze_20261004'
TRAFFIC=CORE/'tomtom_15min_frozen_2025-12-08_2025-12-31.csv'
B01=ROOT/'outputs/Manuscript_Execution_20261006_b01_054939Z/batch01_preflight'
QA=[]
F='%Y-%m-%d %H:%M:%S'
def parse(s):return datetime.strptime(s,F)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,x,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x)
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def check(name,ok,detail=''):
    QA.append(dict(check=name,status='PASS' if ok else 'FAIL',detail=str(detail)))
    if not ok:raise AssertionError(name+': '+str(detail))
def quantile(values,p):
    a=sorted(values);v=(len(a)-1)*p;i=math.floor(v);j=math.ceil(v)
    return a[i]+(a[j]-a[i])*(v-i)
def table(data,fields):
    return '| '+' | '.join(fields)+' |\n| '+' | '.join(['---']*len(fields))+' |\n'+'\n'.join('| '+' | '.join(str(r[f]) for f in fields)+' |' for r in data)

def main():
    if (OUT/'BATCH06_ACCEPTANCE_CN.md').exists():raise RuntimeError('Refusing to overwrite finalized delivery')
    source={};by_id={};training=Counter();late=[]
    for ident,r in enumerate(read(TRAFFIC),1):
        node=r['node_id'];slot=parse(r['interval_timestamp_local']);cap=parse(r['capture_time_local']);v=float(r['current_speed_kmh'])
        valid=math.isfinite(v) and r['raw_observed_flag']=='YES' and r['imputed_flag']=='NO'
        source[(node,slot)]=(ident,cap,valid);by_id[ident]=(node,slot,cap)
        if datetime(2025,12,8)<=slot<datetime(2025,12,24) and cap<datetime(2025,12,24) and valid:training[node]+=1
        if cap>slot+timedelta(minutes=15):late.append((node,r['source_file'],r['source_row_number'],r['interval_timestamp_local'],r['capture_time_local']))
    # The main audit's compatibility fallback compares the late count. This test verifies full identities.
    prior_late={(r['node_id'],r['source_file'],r['source_row_number'],r['interval_timestamp_local'],r['capture_time_local']) for r in read(B01/'TIME_FIELD_ANOMALIES.csv') if r['reason']=='ANCHOR_UNAVAILABLE_AT_SLOT_PLUS15'}
    check('late_records_exact_source_keys',set(late)==prior_late and len(late)==9)
    check('unique_observation_keys',len(source)==len(by_id)==90929)
    nodes=sorted(r['node_id'] for r in read(CORE/'tomtom_node_master_51.csv'))
    config=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    availability={r['node_id']:r for r in read(OUT/'TRAINING_AVAILABILITY_STRATA.csv')}
    values=[training[node]/1536 for node in nodes];q1=quantile(values,1/3);q2=quantile(values,2/3)
    check('linear_quantile_thresholds',abs(q1-config['q1'])<1e-14 and abs(q2-config['q2'])<1e-14)
    strata={}
    for node in nodes:
        a=training[node]/1536;layer='Low' if a<=q1 else 'Medium' if a<=q2 else 'High';strata[node]=layer
        r=availability[node]
        check('training_availability:'+node,int(r['expected_training_positions'])==1536 and int(r['existing_training_records'])==int(r['cutoff_visible_records'])==training[node] and int(r['unknown_or_late_capture_records'])==0 and abs(float(r['availability'])-a)<1e-14 and r['stratum']==layer)
    exported_summary={(int(r['H_h']),r['partition']):r for r in read(OUT/'SAMPLE_SUPPORT_SUMMARY.csv')}
    exported_layers={(int(r['H_h']),r['partition'],r['stratum']):r for r in read(OUT/'STRATIFIED_SUPPORT_SUMMARY.csv')}
    test_sets={};late_input_counts=[]
    for H in [1,3,6]:
        offsets=[('lag1',-15),('lag2',-30),('lag3',-45),('lag4',-60),('seasonal',H*60-1440)]
        reference_rows=read(OUT/f'samples/H{H}_REFERENCE_AUDIT.csv')
        reference={(r['node_id'],parse(r['origin'])):r for r in reference_rows}
        issuable_rows=read(OUT/f'samples/H{H}_ISSUABLE_KEYS.csv');issuable={(r['node_id'],parse(r['origin'])):r for r in issuable_rows}
        score_rows=read(OUT/f'samples/H{H}_SCORABLE_KEYS.csv');score={(r['node_id'],parse(r['origin'])):r for r in score_rows}
        computed_ready={};computed_score={};seen=set();support=defaultdict(Counter);layer_counts=defaultdict(Counter);node_sets=defaultdict(set);dates=defaultdict(set);layer_nodes=defaultdict(set);layer_dates=defaultdict(set);all_checks=Counter();not_yet_visible=Counter()
        for r in read(OUT/f'samples/H{H}_INPUT_ADMISSION.csv'):
            node=r['node_id'];origin=parse(r['origin']);target=origin+timedelta(hours=H);key=(node,origin);partition=r['partition'];end=datetime.fromisoformat(config['partitions_left_closed_right_open'][partition][1]);start=datetime.fromisoformat(config['partitions_left_closed_right_open'][partition][0])
            all_checks['origin_and_target']+=int(start<=origin<end and parse(r['target'])==target and int(r['H_h'])==H and r['stratum']==strata[node] and origin.minute%15==0 and origin.second==0 and key not in seen);seen.add(key)
            same=target<end;states=[];ids=[]
            for role,offset in offsets:
                original=source.get((node,origin+timedelta(minutes=offset)))
                state='MISSING' if original is None else ('INVALID_ORIGINAL' if not original[2] else ('NOT_YET_VISIBLE' if original[1]>origin else 'OK'))
                states.append(state);ids.append(original[0] if original else None)
                all_checks['input_status_'+role]+=int(r[role+'_status']==state and r[role+'_record_id']==(str(original[0]) if original else ''))
                if state=='NOT_YET_VISIBLE':not_yet_visible[(partition,role)]+=1
            primary=next((role+':'+state for (role,_),state in zip(offsets,states) if state!='OK'),'OK')
            ready=same and primary=='OK'
            all_checks['input_ready_independent_of_target']+=int(r['same_partition']==str(same) and r['input_primary_status']==primary and r['input_ready']==str(ready))
            target_record=source.get((node,target))
            ref='MISSING_REFERENCE' if target_record is None else ('REFERENCE_NOT_FUTURE' if target_record[1]<=origin else ('REFERENCE_AFTER_PARTITION_CUTOFF' if partition!='test' and target_record[1]>=end else 'OK'))
            rr=reference[key]
            all_checks['future_reference']+=int(rr['reference_status']==ref and rr['reference_record_id']==(str(target_record[0]) if target_record else '') and parse(rr['target'])==target and rr['partition']==partition and rr['stratum']==strata[node])
            s=support[partition];s['candidate_decisions']+=1;s['cross_partition_targets']+=int(not same);s['same_partition_candidates']+=int(same);s['all_five_inputs_visible']+=int(primary=='OK');s['input_ready']+=int(ready);s['input_not_ready_within_partition']+=int(same and not ready)
            l=layer_counts[(partition,strata[node])];l['candidate_decisions']+=1;l['same_partition_candidates']+=int(same);l['input_ready']+=int(ready)
            if ready:
                computed_ready[key]=ids
                if ref=='OK':
                    computed_score[key]=target_record[0];s['scorable']+=1;l['scorable']+=1;node_sets[partition].add(node);dates[partition].add(target.date());layer_nodes[(partition,strata[node])].add(node);layer_dates[(partition,strata[node])].add(target.date())
                else:s['ready_without_valid_reference']+=1
        check(f'all_decisions_H{H}',len(seen)==117504 and len(reference)==len(reference_rows)==117504)
        for item,count in all_checks.items():check(f'every_row:{item}:H{H}',count==117504)
        check(f'issuable_keys_H{H}',set(issuable)==set(computed_ready) and len(issuable_rows)==len(issuable) and all([int(issuable[key][role+'_record_id']) for role,_ in offsets]==ids for key,ids in computed_ready.items()))
        check(f'scorable_keys_H{H}',set(score)==set(computed_score) and len(score_rows)==len(score) and all(int(score[key]['reference_record_id'])==ident for key,ident in computed_score.items()))
        for partition,s in support.items():
            r=exported_summary[(H,partition)]
            check(f'summary_counts_H{H}:{partition}',all(int(r[field])==s[field] for field in ['candidate_decisions','cross_partition_targets','same_partition_candidates','all_five_inputs_visible','input_ready','input_not_ready_within_partition','ready_without_valid_reference','scorable']) and int(r['scorable_node_count'])==len(node_sets[partition]) and int(r['target_date_count'])==len(dates[partition]))
            check(f'summary_fractions_H{H}:{partition}',abs(float(r['input_ready_fraction_of_candidates'])-s['input_ready']/s['candidate_decisions'])<1e-14 and abs(float(r['score_fraction_of_ready'])-s['scorable']/s['input_ready'])<1e-14)
            for layer in ['Low','Medium','High']:
                l=layer_counts[(partition,layer)];lr=exported_layers[(H,partition,layer)]
                check(f'layer_support_H{H}:{partition}:{layer}',all(int(lr[field])==l[field] for field in ['candidate_decisions','same_partition_candidates','input_ready','scorable']) and int(lr['scoring_node_count'])==len(layer_nodes[(partition,layer)]) and int(lr['target_date_count'])==len(layer_dates[(partition,layer)]) and int(lr['assigned_node_count'])==sum(x==layer for x in strata.values()))
        test_sets[H]={key for key in computed_score if key[1]>=datetime(2025,12,28)}
        for (partition,role),count in sorted(not_yet_visible.items()):late_input_counts.append(dict(H_h=H,partition=partition,input_role=role,not_yet_visible_candidate_count=count))
    shared=set.intersection(*test_sets.values());exported_shared={(r['node_id'],parse(r['origin'])) for r in read(OUT/'TEST_COMMON_ORIGINS_ALL_H.csv')}
    check('all_H_same_origin_intersection',shared==exported_shared and len(shared)==2504)
    index=read(OUT/'OBSERVATION_RECORD_INDEX.csv')
    check('metadata_index_no_target_speed',len(index)==90929 and 'current_speed_kmh' not in index[0] and all(by_id[int(r['frozen_record_id'])]==(r['node_id'],parse(r['interval_timestamp_local']),parse(r['capture_time_local'])) for r in index))
    for r in read(OUT/'INPUT_LOCK.csv'):check('independent_source_hash:'+Path(r['path']).name,sha(Path(r['path']))==r['sha256_before']==r['sha256_after'])
    write(OUT/'NOT_YET_VISIBLE_INPUT_COUNTS.csv',late_input_counts,['H_h','partition','input_role','not_yet_visible_candidate_count'])
    write(OUT/'INDEPENDENT_QA_CHECKS.csv',QA,['check','status','detail'])
    dump(OUT/'INDEPENDENT_QA.json',{'check_count':len(QA),'failed_count':sum(r['status']=='FAIL' for r in QA),'checked_candidate_rows':352512,'implementation':'standard-library exact-key dictionary lookup; all rows, all five inputs, reference status, issued/scorable keys, split cutoffs, source identities and strata','primary_anomaly_check_limit':'main audit compatibility fallback checks count; independent check validates full source keys','training_performed':False,'performance_computed':False,'finished_at_utc':datetime.now(timezone.utc).isoformat(),'python_executable':sys.executable,'verifier_sha256':sha(Path(__file__))})
    deliver_documents(config)
    manifest=[dict(file=str(p.relative_to(OUT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv','DELIVERY_VERIFY.json']]
    write(OUT/'OUTPUT_MANIFEST.csv',manifest,['file','bytes','sha256']);write(OUT/'SHA256_MANIFEST.csv',manifest,['file','bytes','sha256'])
    archive=OUT.parent/(OUT.name+'.zip')
    if archive.exists():raise RuntimeError('Refusing to overwrite ZIP')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(OUT)).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip();matched=all(hashlib.sha256(z.read(r['file'])).hexdigest()==r['sha256'] for r in manifest)
    result={'main_QA_count':len(read(OUT/'QA_CHECKS.csv')),'independent_QA_count':len(QA),'failed_count':0,'payload_count':len(manifest),'manifest_files_rechecked':all(sha(OUT/r['file'])==r['sha256'] for r in manifest),'zip_test':'PASS' if bad is None else str(bad),'zip_payloads_match':matched,'zip_path':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive)}
    dump(OUT/'DELIVERY_VERIFY.json',result);print(json.dumps(result,ensure_ascii=True,indent=2))

def deliver_documents(config):
    admission=json.loads((OUT/'ADMISSION_SUMMARY.json').read_text(encoding='utf-8'));support=admission['sample_support'];test=[r for r in support if r['partition']=='test']
    human=[{'步长h':r['H_h'],'候选决策':r['candidate_decisions'],'跨分区目标':r['cross_partition_targets'],'输入合格':r['input_ready'],'无有效参照':r['ready_without_valid_reference'],'可评分':r['scorable'],'节点':r['scorable_node_count'],'目标日期':r['target_date_count']} for r in test]
    (OUT/'Figure7a_review_CN.md').write_text('''# Figure 7(a)核对结论

可以进入下一步，未发现影响当前科学表达的实质问题。16个显示值与逐点评分复算后的四方法汇总RMSE一致，样本量300/300/211/17正确；6小时的17缺口、15节点已明确标注。颜色与形状区分清楚，纵轴0–25 km/h、等间距时长类别、无误差棒和无连线符合上批指令。标题、图例、标签与边距未见明显重叠或裁切。

文件为4252×2392 RGB PNG，分辨率元数据约599.9988 dpi。原图只读，本包received_figure保存逐字节副本；没有画图或修改图片。数值证据见FIGURE7A_VALUE_CHECK.csv，图元像素位置检查见FIGURE7A_RASTER_CHECK.csv。像素位置检查使用推断的线性坐标校准，容差6像素，三角形中心有几何偏移；不能用它冒称绘图脚本或实际绘图矩阵已经验证。

保持上批英文图注中的边界：每次单节点受控遮蔽，Linear允许未来右端点，参照为提供方记录而不是地面真值，不同长度样本池不同。6小时低于部分3小时结果不表示长缺口更容易。

目前只收到600 dpi PNG，尚未检查300 dpi PNG、TIFF、SVG及实际绘图脚本；这些文件可在最终图稿汇总时补齐，本轮不要求重画。
''',encoding='utf-8')
    (OUT/'BATCH06_ACCEPTANCE_CN.md').write_text(f'''# 第5.5节预测样本准入核查

日期：2026年10月7日，Australia/Sydney。本轮已接受Figure7(a)并进入预测样本资格阶段。按已确认第12节协议核对全网格352,512条候选决策，仅生成资格/参照/来源元数据，尚未训练模型、选alpha或计算预测误差。固定核心12项载荷及清单哈希一致；原图、Word、核心和前批输出保持原版。

## 准入结论

| 项目 | 状态 | 含义 |
| --- | --- | --- |
| Figure7(a)图面及数值 | 满足 | 16个标签与复算RMSE一致，样本量和有限支持提示完整 |
| E07输入/参照资格实现 | 满足 | 逐条精确时间键、五输入capture≤τ、同分区标签、capture>τ及训练/验证截止检查均核对 |
| E03时间角色 | 部分满足 | 代码和字段支持历史记录时刻代理；真实在线到达、提交和时钟同步仍未证明 |
| 训练/验证/测试样本支持 | 满足 | 各H均非空且覆盖51节点；仅代表历史输入完整、未来有有效参照的子集 |
| 三模型拟合和性能结果 | 尚未完成 | 本轮没有模型、预测、误差、alpha、完成率或CI |
| G2/G3总关口 | 未通过 | 预测执行、全篇同步及投稿事项仍未完成 |

## 测试支持

{table(human,list(human[0]))}

输入合格在查询未来参照之前计算并单独保存，不能因未来缺项而倒推“无法预测”。上表“无有效参照”是已经具有合格输入但无法事后评分的决策数；尚没有实际发出预测。各步长评分量相对输入合格量约{test[0]['score_fraction_of_ready']*100:.2f}%/{test[1]['score_fraction_of_ready']*100:.2f}%/{test[2]['score_fraction_of_ready']*100:.2f}%，这些不是预测准确率。所有19584候选来自51×4×96位置，候选包含边界和缺输入；同分区候选数另见SAMPLE_SUPPORT_SUMMARY.csv。

三个步长均输入合格且均有有效未来参照的共同测试决策为{admission['test_common_scorable_origins_all_H']}个，可供将来相同决策集合的敏感性比较；同一决策仍对应不同目标时刻，不等于独立事件数。

训练、验证、测试可评分条数分别为：1h 20202/6016/5863，3h 20029/5874/5727，6h 19530/5676/5535。这里是正式协议下的新资格清单，不是复原旧图；不得沿用旧图5939/5941/5996或任何旧性能。

## 训练可用率分层

分母固定16×96=1536；训练开始前首日尚未采集的位置仍包含在分母内。q1={config['q1']:.17g}、q2={config['q2']:.17g}，即约{config['q1']*100:.4f}%、{config['q2']*100:.4f}%。Low/Medium/High按原定≤q1、(q1,q2]、>q2规则分别为17/17/17节点；这是实际分位结果，没有按node_id强行拆分并列值。阈值在计算任何验证/测试误差之前冻结。该量只描述本训练窗口观测位置可用率，不能称为预测正确概率、TomTom confidence或节点固有质量。

九条晚到原记录与首批异常源键完全匹配；本批候选中各H均有9条最新锚点尚未可见的决策，按原规则登记，不修改时间或回退锚点。该项是候选输入层计数，可能同时存在其他输入缺失；不要简单从最终评分数扣9来推导过滤量。主脚本兼容分支只比较晚到数量，独立核验补足完整来源键核对。所有候选的五输入状态与未来参照状态均逐条独立复核。

主核查123项、独立核查{len(QA)}项全部PASS。这些PASS仅覆盖明示数据与实施检查，不关闭真实在线语义问题或后续模型步骤。

## 下一步的具体工作

在既定有限记录时刻代理范围内，使用本清单运行Persistence、Seasonal24和每H单独训练的Ridge。Ridge五个速度输入标准化仅用各H合格训练集；日历sin/cos、7个weekday和51节点指示项固定；alpha候选0.1/1/10/100/1000仅按共同验证MAE选取，1e−12内并列选择更大alpha，选后不合并验证重拟合。保留输入合格但缺评分参照的预测及方法失败，之后才计算共同评分总体/三层MAE和RMSE、节点宏平均及共同决策敏感性。

本批bundled Python中scikit-learn未找到，因此原定sklearn Ridge SVD调用尚不能在该运行时执行；这里只确认包不可用，不表示模型无法实现。预测批应先检查已有兼容运行环境，或明确采用可核对的NumPy SVD等价实现并记录实现差异；本轮未安装软件或改变求解协议。

预测执行与复核完成后才提供Figure7(b)文字绘图指令和数据路径。现在没有可填入7(b)的正式性能数值。本轮继续遵守用户偏好，不画图。

## 复查入口

audit_admission.py是主核查程序；verify_and_deliver.py使用标准库精确键字典逐条复算。要重跑，复制这两程序到新的空目录后依次用RUN_CONTEXT.json记录的Python执行，不覆盖本批文件。CONFIG.json定义全部时间键、截止与层阈值。OBSERVATION_RECORD_INDEX.csv用frozen_record_id回指冻结CSV数据记录序号（1为表头后的第一条，不是含表头的文本行号），并保存源文件/源行及记录时刻，不包含速度值。

samples/H*_INPUT_ADMISSION.csv保存全部候选五输入状态与来源ID，H*_ISSUABLE_KEYS.csv是按已知输入和日历边界独立得到的可发出预测键；H*_REFERENCE_AUDIT.csv独立保存所有候选参照状态，H*_SCORABLE_KEYS.csv连接有效未来参照。将来不得直接用SCORABLE_KEYS决定是否发出预测。SAMPLE_SUPPORT_SUMMARY.csv、STRATIFIED_SUPPORT_SUMMARY.csv和EXCLUSION_COUNTS.csv保存分母与原因；输入主排除计数采用日历边界优先、再取第一个不合格输入，逐输入标记另保留，因此不会误将重叠排除相加。

本包为内部研究交付，不构成公开发布、共享许可或投稿准备完成。
''',encoding='utf-8')
    (OUT/'NEXT_FORECAST_STEP_CN.md').write_text('''# 下一批预测执行指令

输入：读取同目录BATCH06_ACCEPTANCE_CN.md、CONFIG.json、INPUT_LOCK.csv、TRAINING_AVAILABILITY_STRATA.csv、samples目录资格清单及锁定的TOMTOM_CORE_20261004。按原定有限记录时刻代理执行，不解释为真实在线性能。

先解决Ridge既定SVD实现的运行环境并记录版本，保持已有五个速度特征、日历编码、每H直接跨节点模型、训练专用标准化、五alpha验证MAE选参和不重拟合规则。输入与未来评分参照分离；使用所有ISSUABLE_KEYS尝试预测，缺未来参照也保留预测。SCORABLE_KEYS只供事后评分，不决定能否发出预测。三方法同H使用相同输入/目标键，任何失败保存状态并披露完成与共同保留量。

保存特征来源、每H缩放参数和模型系数、所有alpha未舍入验证误差、选择记录、三方法逐条预测/状态/参照/误差、总体及三层MAE/RMSE、节点与日期误差、node-macro MAE、2504共同测试决策的跨H比较、中/高比值的分子分母。分层不改变、输入不填补、预测不裁剪、不加入天气/HERE/confidence或自由流速度。

独立复算全部指标和公平性，保存配置、环境、日志、输入输出SHA256、文件清单及ZIP；原核心、图稿和Word不修改。测试只有四天，主报告点估计，不擅自加入CI或显著性结论。

最后提交第5.5节英文草稿与Figure7(b)绘图文字指令和真实数据路径，不实际画图。未执行和不可估计结果不能填数值。
''',encoding='utf-8')

if __name__=='__main__':main()
