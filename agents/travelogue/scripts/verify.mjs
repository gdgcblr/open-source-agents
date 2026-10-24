import {spawnSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
process.chdir(fileURLToPath(new URL('../',import.meta.url)));
const venv=join('.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.TRAVELOGUE_PYTHON||(existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
for(const [cmd,args] of [[python,['-m','unittest','discover','-s','backend/tests','-v']], [python,['-m','backend.evals']], [process.execPath,['scripts/test-ui.mjs']], [process.execPath,['node_modules/typescript/bin/tsc','--noEmit']], [process.execPath,['node_modules/vite/bin/vite.js','build','--configLoader','runner']]]){
 const result=spawnSync(cmd,args,{stdio:'inherit'});if(result.error){console.error(result.error.message);process.exit(1);}if(result.status!==0)process.exit(result.status||1);
}
