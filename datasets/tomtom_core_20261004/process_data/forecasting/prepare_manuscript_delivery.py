"""Prepare verified English text, figure instructions and CSV sources; never plot."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,shutil,zipfile

OUT=Path(__file__).resolve().parent
METHODS=['Persistence','Seasonal24','Ridge'];LEVELS=['Overall','Low','Medium','High']
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def write(p,x,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(x)
def table(data,fields):return '| '+' | '.join(fields)+' |\n| '+' | '.join(['---']*len(fields))+' |\n'+'\n'.join('| '+' | '.join(str(r[f]) for f in fields)+' |' for r in data)

def main():
    if (OUT/'BATCH07_ACCEPTANCE_CN.md').exists():raise RuntimeError('Refusing to overwrite finalized delivery')
    independent=json.loads((OUT/'qa/INDEPENDENT_QA.json').read_text(encoding='utf-8'));run=json.loads((OUT/'RUN_CONTEXT.json').read_text(encoding='utf-8'));cfg=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    assert independent['check_count']==1000 and independent['failed_count']==0 and run['QA_count']==205 and run['failed_count']==0
    metrics=rows(OUT/'results/METRICS_OVERALL_AND_STRATA.csv');mi={(int(r['H_h']),r['stratum'],r['method']):r for r in metrics}
    assert len(metrics)==len(mi)==36
    overall_table=[];stratum_table=[];support=[];claims=[]
    for H in [1,3,6]:
        overall_table.append({'H (h)':H,'N':mi[(H,'Overall','Persistence')]['N_scores'],**{m:f"{float(mi[(H,'Overall',m)]['mae_kmh']):.2f} / {float(mi[(H,'Overall',m)]['rmse_kmh']):.2f}" for m in METHODS}})
        for level in LEVELS:
            r=mi[(H,level,'Persistence')]
            stratum_table.append({'H (h)':H,'Subset':level,'n':r['N_scores'],**{m:f"{float(mi[(H,level,m)]['mae_kmh']):.2f}" for m in METHODS}})
            support.append({field:r[field] for field in ['H_h','stratum','N_scores','assigned_node_count','scoring_node_count','target_date_count','candidate_decisions','same_partition_candidates','input_ready','score_fraction_of_input_ready']})
    for r in metrics:
        for field in ['mae_kmh','rmse_kmh','N_scores','scoring_node_count','input_ready']:
            claims.append(dict(claim_key=f"H{r['H_h']}:{r['stratum']}:{r['method']}:{field}",unrounded_value=r[field],source_path=str(OUT/'results/METRICS_OVERALL_AND_STRATA.csv'),source_key=f"H_h={r['H_h']},stratum={r['stratum']},method={r['method']}",verification='independent point/error and support checks; see qa/INDEPENDENT_QA.json'))
    (OUT/'figure_source').mkdir()
    copies={'results/METRICS_OVERALL_AND_STRATA.csv':'Figure7b_point_estimates.csv','results/COMMON_ORIGIN_ALL_H_METRICS.csv':'Figure7b_common_origin_sensitivity.csv','inputs/TRAINING_AVAILABILITY_STRATA.csv':'Figure7b_training_availability.csv'}
    for source,dest in copies.items():
        shutil.copy2(OUT/source,OUT/'figure_source'/dest);assert sha(OUT/source)==sha(OUT/'figure_source'/dest)
    write(OUT/'figure_source/Figure7b_sample_support.csv',support,list(support[0]))
    write(OUT/'CLAIM_EVIDENCE.csv',claims,list(claims[0]))
    text=f'''## 5.5 Traffic-speed forecasting by training-period observation availability

The forecasting benchmark used original non-imputed 15-minute TomTom speed records and a record-time-constrained retrospective design. At decision time τ, the target was the same node's provider speed snapshot at τ + H, for H = 1, 3 and 6 h. Common eligibility required speeds at τ − 15, −30, −45 and −60 min and the previous-day target-clock speed at τ + H − 24 h. Every input required an exact slot match and capture_time_local ≤ τ. Persistence repeated the τ − 15 min speed, while Seasonal24 used the τ + H − 24 h speed. Future references required capture_time_local > τ. These fields supported a historical record-time proxy; actual online arrival was not established.

Training, validation and test intervals were 8–23, 24–27 and 28–31 December 2025 in Asia/Kuching. Decision and target slots belonged to the same interval, and training and validation references were recorded before their respective cutoffs. Eligible labelled samples numbered 20,202/6,016/5,863 for 1 h, 20,029/5,874/5,727 for 3 h and 19,530/5,676/5,535 for 6 h. For each horizon, Ridge used the five speed features, local minute-of-day sine/cosine terms, seven weekday indicators and 51 node indicators. Speed scaling and model fitting used only the eligible training set. Validation MAE selected alpha = 100, 10 and 10, respectively, from 0.1, 1, 10, 100 and 1,000. Models were not refitted with validation data or updated during testing, and predictions were not clipped.

Input eligibility was determined before attaching future references. On the 19,584 test decision positions per horizon, 7,158, 7,144 and 6,892 had complete visible inputs and satisfied the known calendar boundary. All three methods issued finite predictions on these sets, with no failures. Of these predictions, 1,295, 1,417 and 1,357 lacked a valid future scoring reference and were retained as unscored predictions. The common scored samples were 5,863, 5,727 and 5,535 node-by-origin-by-horizon targets, covering all 51 nodes and four target dates. Method completion and common score retention were 100% within eligible sets; these percentages do not represent coverage of all calendar decision positions. Scored fractions of issued predictions were 81.91%, 80.17% and 80.31%.

The table reports primary pooled MAE / auxiliary pooled RMSE in km/h on the identical scored targets within each horizon.

{table(overall_table,list(overall_table[0]))}

Persistence had the lowest MAE at 1 h (2.00 km/h), while Seasonal24 had the lowest MAE at 3 and 6 h (2.27 and 2.19 km/h). Ridge had the lowest RMSE at every horizon (5.00, 5.38 and 5.40 km/h), but it did not have the lowest primary MAE. The metrics therefore gave different descriptive rankings; these results do not establish uniform Ridge superiority. A sensitivity comparison on 2,504 common test origins across all three horizons preserved these overall MAE and RMSE rankings. Node-macro MAE, per-node and per-target-date errors, and paired method error differences are supplied separately so the pooled estimates can be inspected against node and time composition.

Training-period observation availability was defined on a fixed 1,536-position denominator per node. Linear one-third and two-thirds quantiles were {cfg['q1']*100:.4f}% and {cfg['q2']*100:.4f}%. Applying A ≤ q1, q1 < A ≤ q2 and A > q2 yielded 17 Low, 17 Medium and 17 High nodes without splitting ties. Labels were frozen before validation and test error calculation. Scored counts in these layers were 2,031/1,953/1,879 at 1 h, 2,005/1,899/1,823 at 3 h and 1,927/1,817/1,791 at 6 h. Ridge's Medium/High MAE ratios were 0.931, 1.116 and 1.103, showing that the High layer did not invariably have lower error. Figure 7(b) is intended to present overall and layer-specific MAE point estimates with their actual sample support; the figure has not yet been drawn.

Availability describes observed training-window positions, including the collection start and missingness, rather than measurement accuracy, provider confidence or a probability of correct prediction. The relative layer thresholds are close and specific to these 51 nodes. Layer comparisons are descriptive, with differing traffic, node and time composition, and do not demonstrate that increasing collection availability causes forecast error to decrease. The four test dates and dependent 15-minute targets limit uncertainty inference and generalization. No confidence intervals or significance tests were calculated. Reference speeds remain provider records rather than ground truth, and the benchmark does not validate real online deployment or prediction with naturally incomplete histories.
'''
    (OUT/'Section_5_5_EN.md').write_text(text,encoding='utf-8')
    caption=f'''**Figure 7(b). Record-time-constrained retrospective forecasting by training-period observation availability.** Three horizon panels show pooled MAE for Persistence, Seasonal24 and Ridge on Overall, Low, Medium and High evaluation subsets. Within a horizon all methods share the same scored targets; Overall contains the three availability layers. Common scored counts are n = 5,863, 5,727 and 5,535 at 1, 3 and 6 h. Layer counts are 2,031/1,953/1,879, 2,005/1,899/1,823 and 1,927/1,817/1,791, respectively. Each layer contains 17 training-defined nodes and all four test target dates. Availability uses a fixed 1,536-slot training denominator, with linear tercile thresholds of {cfg['q1']*100:.4f}% and {cfg['q2']*100:.4f}%; ties are not split. The latest speed anchor is τ − 15 min, and every input must have capture_time_local ≤ τ. Targets are same-node provider snapshots at τ + H, with capture_time_local > τ. Ridge uses training-only scaling/fitting and validation-selected alpha values 100/10/10, without validation refitting. Points are descriptive estimates without confidence intervals. Horizons and layers differ in sample composition, and availability is not measurement accuracy or prediction correctness. The design uses a historical record-time proxy rather than verified online arrival, and provider references are not ground truth.
'''
    (OUT/'Figure7b_caption_EN.md').write_text(caption,encoding='utf-8')
    drawing=f'''# Figure 7(b)详细文字绘图指令

本轮只交文字、CSV和英文图注，没有绘制或渲染图片。日期：2026年10月7日，Australia/Sydney。

## 图数、内容、论文位置

准备1个Figure7(b)组件，放在第5.5节，与Figure7(a)的受控重建基准对应。本组件内采用三个并排小坐标区，分别为1 h、3 h、6 h，展示同一预测任务的总体和训练期可用率分层结果。仍保留一个整体子图标号`(b)`，小坐标区使用步长标题，不新增Figure7(c)/(d)或另一张主图。

每个小坐标区横轴有`Overall`、`Low`、`Medium`、`High`四组；每组并排画三方法MAE点估计。Overall是后三层共同评分记录的合计，不是第四个独立层。主图同时回答方法比较、预测步长和层间描述性差异。RMSE保留在正文表格，不与MAE混入同一纵轴系列。

## 布局与映射

- 独立组件默认16:9，180 × 101.25 mm。三个小坐标区等宽约45–48 mm，间距约6–8 mm；先预留统一图例、标题、横轴样本量和页脚，再分配绘图区。目标期刊尺寸优先，未来与7(a)拼版时再次检查实际字号。
- 整体标题建议`Retrospective forecasting by observation availability`，左上角`(b)`。三个小标题分别`1 h`、`3 h`、`6 h`。
- 共用纵轴名称`Pooled MAE (km/h)`；三个区都使用0–4.5 km/h范围，主刻度0、1、2、3、4。当前全部36个点的最高值为3.78646 km/h，不能为了强调差异截断纵轴或各区采用不同尺度。
- 横轴`Evaluation subset`。四组可用位置0、1.4、2.4、3.4，在Overall与Low之间预留稍宽间隔并加淡灰竖虚线；这只帮助区分合计与分层，不表示统计检验。
- 组内固定方法顺序Persistence、Seasonal24、Ridge，横向偏移可取−0.18、0、+0.18。点之间不连线，不拟合随步长或可用率的趋势。
- 颜色/形状同时区分方法：Persistence蓝色#0072B2/圆；Seasonal24橙色#E69F00/方；Ridge紫色#CC79A7/菱形。图例共享一次，置于顶部预留区域。
- 白底、Arial、淡灰水平网格。最终印刷字号8–9 pt，方法点约4.5–5.5 pt，轮廓0.7 pt。标题较长时换行，不缩小到不可读。
- 每组横轴下用第二行显示`n=...`，n为可评分node×origin×H目标条数，不是节点数或独立事件数。三个方法共用该组n，只显示一次。Overall与三层n详见支持表。
- 建议不在36个相近点旁堆满数字；完整核对表保留在本文件及正文/CSV。若增加点值，按统一规则处理每组的三方法、显示两位小数并自动错位，不能只标注最佳方法。作图坐标使用未舍入CSV值。
- 图下短注可写`Training-defined strata; 17 nodes per stratum`。解释阈值和输入可见性主要放英文图注，不把长方法说明挤入绘图区。
- 不画误差棒、95%CI、星号、显著性括号或“Ridge best”等预设标签。本批没有计算统计区间；各节点/日期误差也不能直接拿来给汇总MAE点做CI。

## 主图数据文件和字段

直接读取：`{OUT/'figure_source/Figure7b_point_estimates.csv'}`。

该文件与正式results/METRICS_OVERALL_AND_STRATA.csv逐字节相同，共36行：3个H × 4个subset × 3个方法。必须使用`H_h`分面、`stratum`作为横轴四组、`method`作为颜色/形状、`mae_kmh`作为唯一主纵轴。`N_scores`作为n；`assigned_node_count`与`scoring_node_count`区别节点支持；`target_date_count`为目标日期数。`rmse_kmh`是辅助指标，不可作为MAE。`score_fraction_of_input_ready`是评分参照覆盖比例，不是预测准确率。

样本支持CSV：`{OUT/'figure_source/Figure7b_sample_support.csv'}`，12行，每H/subset一行。

训练阈值和节点标签：`{OUT/'figure_source/Figure7b_training_availability.csv'}`。固定分母1536，q1={cfg['q1']:.17g}、q2={cfg['q2']:.17g}，Low≤q1、Medium(q1,q2]、High>q2。不得把可用率称为confidence、预测正确率或固有道路质量，不按测试结果重分组。

## MAE与n核对表

所有MAE单位km/h；下表仅供标签核对，坐标仍读取CSV未舍入值。

{table(stratum_table,list(stratum_table[0]))}

总体RMSE及MAE的完整并列结果在第5.5节英文正文：1 h最低MAE是Persistence，3/6 h最低MAE是Seasonal24；Ridge在三个H的RMSE最低，但主指标MAE并非最低。图面不能用“Ridge全面最优”的标题或突出方式覆盖这一结果。

## 统计与样本边界

同H三方法使用相同评分键，没有方法失败；输入合格预测分别7158/7144/6892条，其中1295/1417/1357没有有效未来参照，保留为未评分。主图n=5863/5727/5535；方法完成100%不表示全19584候选都能预测，也不是100%准确。

不同H与层的样本构成不同，测试仅4个日期。三个H共同2504个测试决策的敏感性结果另存`{OUT/'figure_source/Figure7b_common_origin_sensitivity.csv'}`；它控制决策集合，但目标时刻仍不同，不把变化全部归因于步长。

同层17个节点不意味着n相同。High层不保证误差更低，例如Ridge 1h的Medium/High MAE比为0.9308，按原结果保留；3h/6h对应1.1159/1.1035。主图展示真实三层误差，不仅显示比值。

预测参照是提供方原观测，不是地面真值。记录字段支持的是回顾性可见性代理，未证明历史系统真实在线到达。降水、HERE、confidence、自由流速度、重建填补数据不参与本预测输入。

## 可直接交给绘图工具的指令

“读取Figure7b_point_estimates.csv，制作一个16:9的Figure7(b)组件，内含并排的1 h、3 h、6 h三个小坐标区。每区横轴按Overall、Low、Medium、High排列，每组画Persistence蓝圆、Seasonal24橙方、Ridge紫菱形三点。纵轴仅用mae_kmh，三坐标区统一0–4.5 km/h，不连线、无误差棒、无显著性符号。Overall与Low之间留稍宽间隔并用淡灰虚线区分合计和分层，不能把Overall当第四个独立层。组下标实际N_scores为n，17 nodes per stratum放短注，长定义放配套英文图注。图例共享一次，文字留足边距，最终印刷字号8–9 pt；不在36个相近点旁强行堆满数字，若加标签则一致处理同组全部方法且不移动数据坐标。使用CSV未舍入值定位，不能复制旧图数值。输出内容一致的PNG/TIFF 300和600 dpi及可编辑SVG，保存实际绘图脚本与图源、文件清单和SHA256。”

## 正式分析证据路径

- 逐条测试评分：`{OUT/'results/TEST_POINT_SCORES.csv'}`。
- 总体和三层指标：`{OUT/'results/METRICS_OVERALL_AND_STRATA.csv'}`。
- 完成率和未评分支持：`{OUT/'results/COMPLETION_COUNTS.csv'}`。
- 所有alpha验证结果：`{OUT/'models/ALPHA_VALIDATION_METRICS.csv'}`。
- 每H选定模型、缩放和特征顺序：`{OUT/'models'}`中的RIDGE_H1/H3/H6.json。
- 逐节点误差/节点宏平均：`{OUT/'results/METRICS_BY_NODE.csv'}`与`{OUT/'results/NODE_MACRO_MAE.csv'}`。
- 逐目标日期及日期×层误差：`{OUT/'results/METRICS_BY_TARGET_DATE.csv'}`与`{OUT/'results/METRICS_BY_TARGET_DATE_STRATUM.csv'}`。
- 配对误差差值：`{OUT/'results/PAIRED_POINT_ERROR_DIFFERENCES.csv'}`。
- 字段、时间和算法配置：`{OUT/'CONFIG.json'}`；独立核对见`{OUT/'qa/INDEPENDENT_QA.json'}`。

## 导出验收

180 × 101.25 mm对应300 dpi约2126×1196像素、600 dpi约4252×2392像素。TIFF建议LZW，SVG保留可编辑文字/标记。检查36点、12个n、方法颜色/形状、轴单位和统一范围，与源CSV完全一致；无错误CI、无越界/重叠/裁切、三个格式内容一致。本批尚未收到或检验Figure7(b)图稿，最终视觉验收待用户绘制后完成。
'''
    (OUT/'Figure7b_drawing_instructions_CN.md').write_text(drawing,encoding='utf-8')
    summary=f'''# 第5.5节预测执行验收

日期：2026年10月7日，Australia/Sydney。已按用户“可以，进入下一步”的授权完成限定回顾性预测、分层、独立核对、英文5.5草稿和Figure7(b)文字指令。没有实际画图，没有修改Word、原图、核心或前批文件。

## 实际结果

{table(overall_table,list(overall_table[0]))}

表内为MAE / RMSE，km/h。主指标MAE的最低方法是1h Persistence、3h/6h Seasonal24；RMSE三H均由Ridge最低。不得写Ridge全面优于基线。alpha仅由验证MAE选出100/10/10，训练样本20202/20029/19530，验证6016/5874/5676，15个候选模型均训练集拟合，选后没有train+validation重拟合。没有裁剪、输入插补、天气/confidence/HERE或测试更新。

每H在所有输入合格键发出三方法预测，再附未来评分参照；无参照记录保留空误差。测试发出数7158/7144/6892，有效共同评分5863/5727/5535，未评分1295/1417/1357；每方法失败0，完成与共同保留率100%只适用于对应合格集合。输入/参照支持分母已保留，不能把这些百分比解释为预测准确率或全网覆盖。

主程序205项QA全部PASS；独立程序1000项全部PASS，检查每条输入/来源/可见性、不同实现的Ridge正规方程系数与SVD结果（1e−8容差）、所有发出预测回放（1e−10）、51375条方法×测试评分及全部总体/节点/日期/分层/比值/宏平均/共同决策和配对指标。独立程序没有导入sklearn；其正规方程计算用于核验，不替代主协议SVD模型。

## 状态和边界

| 项目 | 状态 | 范围 |
| --- | --- | --- |
| E07预测与分层 | 满足当前限定协议 | 实际样本、15候选拟合、3选定模型、全部预测、评分及敏感性已交付 |
| E03真实在线时刻 | 部分满足 | 仍为历史记录时刻代理，未证明真实接收/提交/时钟同步 |
| 第5.5英文草稿 | 已完成候选文本 | 未修改Word，图7(b)引用为预留图号 |
| Figure7(b) | 文字方案及真实CSV已交付 | 还未绘制，待用户图稿后核对 |
| E09可复算性 | 当前批已支持 | 不代表冻结重建或全论文所有分析流水线都已复现 |
| G2/G3 | 未通过 | 全篇图文同步、未关闭空间/补充证据、作者/共享/投稿事项仍需各自核实 |

训练可用率q1/q2约74.9349%/75.6727%，三层实际17/17/17节点，不是预测可靠性概率。Ridge Medium/High MAE比0.931/1.116/1.103，不能推断提高采集可用率会因果降低误差。四测试日期、密集相邻目标和节点依赖限制泛化与区间推断；本批只点估计，无CI/显著性检验。提供方速度不是地面真值，不宣称真实在线性能。

## 文件入口和复跑

Section_5_5_EN.md为英文正文，Figure7b_caption_EN.md为配套图注，Figure7b_drawing_instructions_CN.md包含具体布局、数据字段、核对表和全部路径。figure_source/Figure7b_point_estimates.csv是36行正式指标的逐字节副本；Figure7b_sample_support.csv是12行真实支持表。

要复跑：将run_forecasting.py、verify_forecasting.py、prepare_manuscript_delivery.py复制到一个新的空输出目录。先使用D:\\Python\\python.exe执行run_forecasting.py，再使用独立QA记录的bundled Python执行verify_forecasting.py及prepare_manuscript_delivery.py。环境版本见RUN_CONTEXT.json；核心与资格输入仍指向锁定路径。不要在已有目录重跑，程序拒绝覆写既有执行/验收。输出日志可以保存到同一新目录并在打包前关闭写入。

predictions/H*_ISSUED_PREDICTIONS.csv在附未来参照前保存三方法发出结果；H*_REFERENCE_ATTACHED.csv包含所有发出记录及评分状态，无参照误差为空。features保存原速度特征、五输入来源ID和capture；inputs/OBSERVATION_RECORD_INDEX.csv连接到冻结CSV的原来源。models保存特征顺序、缩放、系数、截距、所有alpha验证误差和选择；results保存全部可复算误差和支持。

本包是内部研究交付，不改变共享许可或发布状态。最终图稿由用户绘制，后续任何画图需求继续仅给文字/指令和路径。
'''
    (OUT/'BATCH07_ACCEPTANCE_CN.md').write_text(summary,encoding='utf-8')
    for filename in ['Section_5_5_EN.md','Figure7b_caption_EN.md','Figure7b_drawing_instructions_CN.md','BATCH07_ACCEPTANCE_CN.md']:assert (OUT/filename).stat().st_size>0
    manifest=[dict(file=str(p.relative_to(OUT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv','DELIVERY_VERIFY.json']]
    write(OUT/'OUTPUT_MANIFEST.csv',manifest,['file','bytes','sha256']);write(OUT/'SHA256_MANIFEST.csv',manifest,['file','bytes','sha256'])
    archive=OUT.parent/(OUT.name+'.zip')
    if archive.exists():raise RuntimeError('Refusing to overwrite ZIP')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file():z.write(p,str(p.relative_to(OUT)).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip();matched=all(hashlib.sha256(z.read(r['file'])).hexdigest()==r['sha256'] for r in manifest)
    local=all(sha(OUT/r['file'])==r['sha256'] for r in manifest)
    assert bad is None and matched and local
    result=dict(build_QA_count=205,independent_QA_count=1000,failed_count=0,payload_count=len(manifest),payload_hashes_match=local,zip_test='PASS',zip_payloads_match=matched,zip_path=str(archive),zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),completed_at_utc=datetime.now(timezone.utc).isoformat(),figures_rendered=0,word_edited=False)
    dump(OUT/'DELIVERY_VERIFY.json',result);print(json.dumps(result,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
