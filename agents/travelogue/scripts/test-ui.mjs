import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import ts from 'typescript';

async function load(name){
 const source=readFileSync(new URL(`../frontend/src/${name}.ts`,import.meta.url),'utf8');
 const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
 return import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'));
}
const {progressSummary,stageState,elapsedSeconds,clockLabel}=await load('progress');
const base={id:'test',status:'running',stage:'season_researcher',stages:['destination_researcher','season_researcher'],provider:'ollama',stage_states:{destination_researcher:'running',season_researcher:'running',itinerary_planner:'pending',trip_reviewer:'pending',validation:'pending'}};
assert.equal(progressSummary(base).completed,0,'Starting a stage does not complete it');
assert.equal(progressSummary(base).active.length,2,'Parallel workers both remain visible');
assert.match(progressSummary(base).headline,/places.*season/);
const failed={...base,status:'failed',stage_states:{...base.stage_states,destination_researcher:'completed',season_researcher:'failed'}};
assert.equal(progressSummary(failed).completed,1,'A failure must not fill the bar');
assert.equal(progressSummary(failed).busy,false,'Failure stops rolling animation');
assert.equal(progressSummary(failed).failed[0].id,'season_researcher');
assert.equal(stageState({...base,stage_states:undefined},'destination_researcher'),'pending','Legacy runs do not invent completion states');
assert.equal(elapsedSeconds({...base,started_at:'2026-10-24T10:00:00Z',finished_at:'2026-10-24T10:02:05Z'},Date.now()),125,'Finished elapsed time does not keep increasing');
assert.equal(clockLabel(125),'2:05');
assert.equal(elapsedSeconds(base,Date.now()),null,'Old runs without timestamps do not show a fabricated clock');
const {popupPosition,project}=await load('mapGeometry');
for(const [width,height,x,y] of [[900,480,880,450],[320,300,310,280],[1400,900,5,5]]){
 const p=popupPosition(width,height,x,y);
 assert.ok(p.left>=0&&p.left+p.width<=width,'Pop-out fits horizontally');
 assert.ok(p.top>=0&&p.top+p.maxHeight<=height,'Pop-out fits vertically');
}
assert.deepEqual(project(0,0),[500,235]);
console.log('UI logic checks passed: real stage progress, terminal states, elapsed time, popup edges, and map projection.');

const {WORLD_VIEW,constrainView,zoomView,fitPlaces,memoryStops,memoryTrail,memoryThumbnail}=await load('mapGeometry');
const enlarged=zoomView(WORLD_VIEW,2);
assert.equal(enlarged.width,500);
assert.deepEqual(zoomView(WORLD_VIEW,.1),WORLD_VIEW,'Zooming out stops at the world boundary');
assert.equal(zoomView(enlarged,100).width,125,'Zooming in has a readable maximum');
const panned=constrainView({x:-200,y:999,width:500,height:235});
assert.equal(panned.x,0);assert.equal(panned.y,235,'Panning cannot lose the map outside its bounds');
const anchor=[350,200],anchored=zoomView({x:100,y:50,width:600,height:282},1.5,anchor);
assert.ok(Math.abs((anchor[0]-100)/600-(anchor[0]-anchored.x)/anchored.width)<.00001,'Zoom preserves the pointer anchor');
const places=[{id:'west',lon:12,lat:42,image:'/art/coast.svg'},{id:'east',lon:135,lat:35,image:'/art/temples.svg'}];
const recorded=[{id:'late',place_id:'east',visited_on:'2026-04-01',media:[]},{id:'early',place_id:'west',visited_on:'2025-09-01',media:[]},{id:'unknown',place_id:'missing',visited_on:'2024-01-01',media:[]}];
const stops=memoryStops(recorded,places);
assert.deepEqual(stops.map(s=>s.entry.id),['early','late'],'The trail follows dates, not API list order');
assert.equal(recorded[0].id,'late','Chronological sorting does not mutate application data');
assert.equal(memoryTrail(stops).length,1,'Only recorded, located memories form connections');
assert.equal(memoryTrail([{entry:{},place:places[0]},{entry:{},place:places[0]}]).length,0,'Repeated consecutive places do not form fabricated segments');
assert.equal(memoryTrail([{entry:{},place:{id:'a',lon:179,lat:10}},{entry:{},place:{id:'b',lon:-179,lat:10}}]).length,0,'Date-line crossings do not draw a misleading line across the world');
const fit=fitPlaces(places);
for(const place of places){const [x,y]=project(place.lon,place.lat);assert.ok(x>=fit.x&&x<=fit.x+fit.width&&y>=fit.y&&y<=fit.y+fit.height,'Fit memories keeps every stop visible');}
assert.deepEqual(fitPlaces([]),WORLD_VIEW,'Empty journals show the world');
assert.equal(memoryThumbnail(recorded[0],places[1]),'/art/temples.svg','No uploaded photo uses the labeled illustration');
assert.equal(memoryThumbnail({media:[{id:'video',mime:'video/mp4'},{id:'actual-photo',mime:'image/jpeg'}]},places[0]),'/api/media/actual-photo','User photos take precedence over illustration fallbacks');
console.log('Journey map checks passed: zoom/pan limits, anchor stability, chronological connections, dateline handling, fit bounds, and real-photo selection.');
