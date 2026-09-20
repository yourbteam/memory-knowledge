from pathlib import Path
import subprocess,json
root=Path(__file__).resolve().parent
expected='sha256:1b344156b2600b667d560dbf81fff1cbe6e6df63b5f82e4b06e7602afc13a38f'
base=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','taggable-provenance-prototype-app:latest'],text=True).strip()
if base!=expected:raise SystemExit('Base image changed; inspect before rebuilding')
subprocess.run(['docker','build','--pull=false','--file',str(root/'image/Dockerfile.runtime'),'--tag','atom-builder-php74-python:20260920',str(root/'image')],check=True)
image=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}','atom-builder-php74-python:20260920'],text=True).strip()
p=subprocess.run(['docker','run','--rm','--pull=never','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--entrypoint','python3',image,'-c','import subprocess,json; print(json.dumps({"python":__import__("sys").version,"php":subprocess.check_output(["php","-r","echo PHP_VERSION;"],text=True)}))'],capture_output=True,text=True,check=True)
(root/'image.json').write_text(json.dumps({'base':base,'image':image,'verified':json.loads(p.stdout)},indent=2)+'\n')
print(p.stdout)
