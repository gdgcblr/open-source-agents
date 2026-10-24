import {spawnSync} from 'node:child_process';
import {existsSync,copyFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));process.chdir(root);
function run(command,args){const r=spawnSync(command,args,{stdio:'inherit'});if(r.error)throw r.error;if(r.status!==0)process.exit(r.status||1);}
const py=process.platform==='win32'?'python':'python3';
if(!existsSync('.env'))copyFileSync('.env.example','.env');
if(!existsSync('.venv'))run(py,['-m','venv','.venv']);
const python=join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
run(python,['-m','pip','install','-r','requirements.txt']);
run(process.platform==='win32'?'npm.cmd':'npm',['ci']);
run(python,['-c','from backend.storage import Store; from pathlib import Path; Store(Path(".runtime")); print("Demo journal ready.")']);
console.log('Setup complete. Run npm run dev. To use Gemma, follow the Ollama section in README.md.');
