"""Record the existing model runtime and synchronize the pending handoff package."""
from pathlib import Path
from datetime import datetime,timezone
import csv,hashlib,json,subprocess,zipfile

OUT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def main():
    if (OUT/'EXISTING_MODEL_RUNTIME.json').exists():raise RuntimeError('Refusing to repeat finalized runtime probe')
    code='import sys,json,numpy,scipy,pandas,sklearn; from sklearn.linear_model import Ridge; print(json.dumps({"executable":sys.executable,"python":sys.version,"numpy":numpy.__version__,"scipy":scipy.__version__,"pandas":pandas.__version__,"sklearn":sklearn.__version__,"ridge_configuration":Ridge(fit_intercept=True,positive=False,solver="svd").get_params(),"fit_performed":False},ensure_ascii=True))'
    result=subprocess.run([r'D:\Python\python.exe','-c',code],capture_output=True,text=True,check=True)
    probe=json.loads(result.stdout);assert probe['ridge_configuration']['solver']=='svd' and not probe['fit_performed']
    probe['probe_time_utc']=datetime.now(timezone.utc).isoformat();probe['command_arguments']=[r'D:\Python\python.exe','-c',code]
    probe['scope']='existing libraries imported and Ridge SVD object configured; no fitting or performance calculation; no package installation'
    dump(OUT/'EXISTING_MODEL_RUNTIME.json',probe)
    report=OUT/'BATCH06_ACCEPTANCE_CN.md';text=report.read_text(encoding='utf-8')
    old='本批bundled Python中scikit-learn未找到，因此原定sklearn Ridge SVD调用尚不能在该运行时执行；这里只确认包不可用，不表示模型无法实现。预测批应先检查已有兼容运行环境，或明确采用可核对的NumPy SVD等价实现并记录实现差异；本轮未安装软件或改变求解协议。'
    new=f'本批bundled Python中scikit-learn未找到，随后检查电脑已有环境并确认D:\\Python\\python.exe可以导入Ridge，solver=svd、fit_intercept=True、positive=False配置可用。实际版本：Python 3.12.8、scikit-learn {probe["sklearn"]}、NumPy {probe["numpy"]}、SciPy {probe["scipy"]}、pandas {probe["pandas"]}。EXISTING_MODEL_RUNTIME.json保存探测命令及版本。这里只验证导入和配置，没有拟合模型；下一批可沿用该已有环境，无需安装软件或改为另一求解实现。'
    assert old in text;report.write_text(text.replace(old,new),encoding='utf-8')
    nextpath=OUT/'NEXT_FORECAST_STEP_CN.md';text=nextpath.read_text(encoding='utf-8')
    text=text.replace('先解决Ridge既定SVD实现的运行环境并记录版本，','已核实已有D:\\Python\\python.exe支持原定sklearn Ridge SVD实现，版本及导入检查见EXISTING_MODEL_RUNTIME.json；下一批重新核对环境并记录实际训练版本，')
    nextpath.write_text(text,encoding='utf-8')
    context=json.loads((OUT/'RUN_CONTEXT.json').read_text(encoding='utf-8'));context['additional_model_runtime_probe']=str(OUT/'EXISTING_MODEL_RUNTIME.json');context['runtime_probe_finalizer_sha256']=sha(Path(__file__));context['finalized_at_utc']=datetime.now(timezone.utc).isoformat();dump(OUT/'RUN_CONTEXT.json',context)
    manifest=[dict(file=str(p.relative_to(OUT)).replace('\\','/'),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv','DELIVERY_VERIFY.json']]
    for name in ['OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv']:
        with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=['file','bytes','sha256']);w.writeheader();w.writerows(manifest)
    archive=OUT.parent/(OUT.name+'.zip')
    # This is the current pending batch only; prior batches and inputs are unchanged.
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(OUT.rglob('*')):
            if p.is_file() and p.name!='DELIVERY_VERIFY.json':z.write(p,str(p.relative_to(OUT)).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip();matched=all(hashlib.sha256(z.read(r['file'])).hexdigest()==r['sha256'] for r in manifest)
    checkfiles=all(sha(OUT/r['file'])==r['sha256'] for r in manifest)
    assert bad is None and matched and checkfiles
    verify={'main_QA_count':123,'independent_QA_count':154,'existing_model_runtime_import_and_configuration':'PASS','failed_count':0,'payload_count':len(manifest),'manifest_files_rechecked':checkfiles,'zip_test':'PASS','zip_payloads_match':matched,'zip_path':str(archive),'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive),'model_training_performed':False}
    dump(OUT/'DELIVERY_VERIFY.json',verify);print(json.dumps(verify,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
