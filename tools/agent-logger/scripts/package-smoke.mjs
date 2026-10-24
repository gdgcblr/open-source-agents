import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync } from 'node:zlib';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const metadata = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const run = (file, args, cwd = root) =>
  execFileSync(file, args, {
    cwd,
    encoding: 'utf8',
    timeout: 120000,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
const [packed] = JSON.parse(run(npm, ['pack', '--ignore-scripts', '--json']));
assert.ok(
  packed.files.every(({ path }) =>
    /^(dist\/|README\.md$|LICENSE$|package\.json$)/u.test(path),
  ),
);
const archive = gunzipSync(await readFile(join(root, packed.filename)));
assert.ok(
  !packed.files.some(({ path }) => path.endsWith('.map')),
  'Source maps must not be published.',
);
assert.ok(
  ![homedir(), tmpdir(), root].some((path) => archive.includes(Buffer.from(path))),
  'Private machine path leaked into package.',
);
assert.ok(
  !archive.includes(Buffer.from('sourceMappingURL=')),
  'Package still references a source map.',
);
if (process.env.GOOGLE_API_KEY?.trim())
  assert.ok(
    !archive.includes(Buffer.from(process.env.GOOGLE_API_KEY)),
    'API key leaked into package.',
  );
assert.equal(
  Object.keys(metadata.dependencies ?? {}).length,
  0,
  'Core must have zero runtime dependencies.',
);
const directory = await mkdtemp(join(tmpdir(), 'agent-logger-package-'));

try {
  run(npm, [
    'install',
    '--prefix',
    directory,
    '--omit=dev',
    '--ignore-scripts',
    '--no-audit',
    '--no-fund',
    join(root, packed.filename),
  ]);
  await writeFile(join(directory, 'consumer.mjs'), coreConsumer(metadata.name));
  const core = run(process.execPath, ['consumer.mjs'], directory).trim();
  await writeFile(
    join(directory, 'consumer.cjs'),
    `import(${JSON.stringify(metadata.name)}).then(async ({createAgentLogger})=>{const logger=await createAgentLogger({sink:{write:()=>{}}});await logger.run('cjs',()=>42);if(!(await logger.close()).success)process.exitCode=1;}).catch(()=>{process.exitCode=1;});`,
  );
  run(process.execPath, ['consumer.cjs'], directory);
  await writeFile(join(directory, 'consumer.mts'), typedConsumer(metadata.name));
  run(
    process.execPath,
    [
      join(root, 'node_modules/typescript/bin/tsc'),
      '--strict',
      '--noEmit',
      '--module',
      'NodeNext',
      '--target',
      'ES2023',
      '--skipLibCheck',
      '--types',
      'node',
      '--typeRoots',
      join(root, 'node_modules/@types'),
      'consumer.mts',
    ],
    directory,
  );
  run(npm, [
    'install',
    '--prefix',
    directory,
    '--ignore-scripts',
    '--no-audit',
    '--no-fund',
    '@google/adk@2.3.0',
  ]);
  await writeFile(join(directory, 'adk.mjs'), adkConsumer(metadata.name));
  const adk = run(process.execPath, ['adk.mjs'], directory).trim();
  console.log(
    JSON.stringify(
      {
        package: metadata.name,
        version: metadata.version,
        archive: packed.filename,
        bytes: packed.size,
        core,
        types: 'passed',
        commonJsDynamicImport: 'passed',
        adk,
      },
      null,
      2,
    ),
  );
} finally {
  await rm(directory, { recursive: true, force: true });
}

function coreConsumer(name) {
  return `import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createAgentLogger,readLog} from ${JSON.stringify(name)};
const logger=await createAgentLogger();
const tool=logger.wrapTool('answer',value=>value*2);
assert.equal(await logger.run('task',()=>tool(21)),42);
assert.equal((await logger.close()).success,true);
assert.equal((await readLog(logger.filePath)).length,4);
assert.match(execFileSync('./node_modules/.bin/agent-logger',['view',logger.filePath],{encoding:'utf8'}),/Events: 4/);
console.log('SDK, local files, reader and installed CLI passed');`;
}

function typedConsumer(name) {
  return `import {createAgentLogger, type AgentSpan} from ${JSON.stringify(name)};
const logger=await createAgentLogger({sink:{write:()=>{}}});
const tool=logger.wrapTool('length',(text:string):number=>text.length);
const result:Promise<number>=tool('typed');
await logger.trace('model','model',(span:AgentSpan)=>span.recordUsage('gemini',{}));
await result; await logger.close();`;
}

function adkConsumer(name) {
  return `import assert from 'node:assert/strict';
import {BaseLlm,LlmAgent,FunctionTool,Runner,InMemorySessionService} from '@google/adk';
import {createAgentLogger} from ${JSON.stringify(name)};
import {AgentLoggerPlugin} from ${JSON.stringify(name + '/adk')};
class FixtureModel extends BaseLlm {
  calls=0;
  constructor(){super({model:'offline-fixture'});}
  async *generateContentAsync(){
    this.calls++;
    const parts=this.calls===1?[{functionCall:{id:'tool-1',name:'echo',args:{}}}]:[{text:'packed agent complete'}];
    yield {content:{role:'model',parts},usageMetadata:{promptTokenCount:2,candidatesTokenCount:3,totalTokenCount:5}};
  }
  async connect(){throw new Error('Live fixture unsupported');}
}
const events=[];
const logger=await createAgentLogger({sink:{write:event=>{events.push(event);}}});
const plugin=new AgentLoggerPlugin(logger);
const agent=new LlmAgent({name:'fixture',model:new FixtureModel(),tools:[new FunctionTool({name:'echo',description:'Offline test tool',execute:()=>({ok:true})})]});
const runner=new Runner({appName:'fixture',agent,plugins:[plugin],sessionService:new InMemorySessionService(),autoCreateSession:true});
let answer='';for await(const event of runner.runAsync({userId:'test',sessionId:'test',newMessage:{role:'user',parts:[{text:'run'}]}})){for(const part of event.content?.parts??[]){if(part.text)answer+=part.text;}}
assert.match(answer,/packed agent complete/);assert.equal((await plugin.close()).success,true);
assert.equal(events.filter(event=>event.kind==='tool'&&event.status==='completed').length,1);
assert.equal(events.filter(event=>event.kind==='model'&&event.status==='completed').length,2);
console.log('Packed ADK plugin, model, tool, usage and shutdown passed');`;
}
