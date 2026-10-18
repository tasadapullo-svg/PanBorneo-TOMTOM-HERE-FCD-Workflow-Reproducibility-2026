from pathlib import Path
import argparse, csv, hashlib, shutil, subprocess, sys, tempfile

base = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description='Restore original input layout and call the unchanged core builder.')
parser.add_argument('--output-dir', type=Path, required=True)
args = parser.parse_args()
destination = args.output_dir.resolve()
if destination.exists():
    raise SystemExit('Choose a new output directory; existing output is never overwritten.')
with (base/'metadata/FROZEN_INPUT_MAP.csv').open(encoding='utf-8-sig', newline='') as f:
    entries = list(csv.DictReader(f))
with tempfile.TemporaryDirectory(prefix='pb_source_') as tmp:
    restored = Path(tmp)
    for e in entries:
        source = base/e['packaged_path']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == e['sha256'], e['packaged_path']
        target = restored/e['original_relative_path']
        assert target.resolve().is_relative_to(restored.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(base/'core/LICENSE_NOTICE.md', restored/'LICENSE_NOTICE.md')
    subprocess.run([sys.executable, str(base/'core/build_tomtom_core_freeze.py'),
                    '--source-root', str(restored), '--output-dir', str(destination)], check=True)
