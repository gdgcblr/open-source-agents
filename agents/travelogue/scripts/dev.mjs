import {spawn} from 'node:child_process';
import {existsSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
const root=fileURLToPath(new URL('../',import.meta.url));process.chdir(root);
const venv=join(root,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
const python=process.env.TRAVELOGUE_PYTHON||(existsSync(venv)?venv:process.platform==='win32'?'python':'python3');
const children=[];let stopping=false;
function stop(code=0){if(stopping)return;stopping=true;for(const child of children)child.kill('SIGTERM');setTimeout(()=>process.exit(code),400).unref();}
function start(command,args){const child=spawn(command,args,{stdio:'inherit',cwd:root});children.push(child);child.on('error',e=>{console.error(e.message);stop(1);});child.on('exit',code=>{if(!stopping)stop(code||0);});}
start(python,['-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8000']);
start(process.execPath,['node_modules/vite/bin/vite.js','--configLoader','runner']);
console.log('Travelogue: http://127.0.0.1:5173 · API: http://127.0.0.1:8000/docs');
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());
