"""Build a portable release with the exact data required by the application."""
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

root=Path(__file__).resolve().parents[1]
out=root.parent/'comparison_release'
out.mkdir(exist_ok=True)
archive=out/'travel_comparison_complete.zip'
selected=[]
for folder in ['src','scripts','tests','eval','frontend/src','frontend/public','frontend/dist','data/places','data/weather']:
    for p in (root/folder).rglob('*'):
        if not p.is_file() or any(part in {'__pycache__','results','raw','.pytest_cache'} for part in p.relative_to(root).parts):continue
        if p.suffix in {'.pyc'}:continue
        selected.append(p)
for name in ['pyproject.toml','.env.example','.gitignore','docs/AGENTS.md','docs/PRODUCT.md','docs/DESIGN.md','.impeccable/design.json',
             'README.md','requirements-comparison-lock.txt','data/inventory.json','data/README_COMPARISON_DATA_HE.md',
             'frontend/package.json','frontend/package-lock.json','frontend/tsconfig.json','frontend/vite.config.mjs','frontend/index.html',
             'web/scenarios.json','web/recorded_baseline.json','web/smoke_report.json','web/test_report.txt','web/design_detection.json']:
    p=root/name
    if p.exists():selected.append(p)
selected=sorted(set(selected))
manifest={
 'title':'Travel comparison — code / one CrewAI agent / three CrewAI agents',
 'source_repository':'https://github.com/Noven2155/Travel_Agent',
 'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'local_branch':'feat/comparison-studio',
 'ui_url':'https://travel-comparison-lab-galit.galitneu.chatgpt.site',
 'catalog_sha256':hashlib.sha256((root/'data/inventory.json').read_bytes()).hexdigest(),
 'real_model_tested':False,
 'files':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()for p in selected}}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
 for p in selected:z.write(p,'travel_comparison/'+str(p.relative_to(root)))
 z.writestr('travel_comparison/README_HE.md',(root/'README.md').read_bytes())
 z.writestr('travel_comparison/RELEASE_MANIFEST.json',json.dumps(manifest,indent=2,ensure_ascii=False))
with zipfile.ZipFile(archive) as z:
 assert z.testzip() is None
 assert 'travel_comparison/frontend/dist/index.html' in z.namelist()
 assert 'travel_comparison/data/inventory.json' in z.namelist()
 assert not any('node_modules' in n or '/runtime/' in n or '/.env'==n[-5:] for n in z.namelist())
print(json.dumps({'path':str(archive),'bytes':archive.stat().st_size,'files':len(selected),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
