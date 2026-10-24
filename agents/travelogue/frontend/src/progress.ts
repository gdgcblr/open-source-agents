import type {Run,StageState} from './types';

export const STEPS = [
  {id:'destination_researcher',label:'Discover',detail:'Finding places for your story',messages:['Every great trip starts with a little curiosity.','Looking beyond the postcard, one place at a time.','Making room for the places you haven’t met yet.']},
  {id:'season_researcher',label:'Find the season',detail:'Looking at seasonal tradeoffs',messages:['A little sunshine? A quieter season? Let’s explore.','Some places have a season. Others have a feeling.','Looking for the right time for your kind of journey.']},
  {id:'itinerary_planner',label:'Connect the dots',detail:'Building your day-by-day itinerary',messages:['Good days need breathing room. We’re leaving some.','Connecting the dots, with room for a detour.','A few plans. A little wandering. Finding your balance.','Your next chapter is taking shape, one day at a time.']},
  {id:'trip_reviewer',label:'A second look',detail:'Reviewing the draft and its assumptions',messages:['One more look before the adventure begins.','Giving the little details a little extra attention.','The best travel companion? A thoughtful second opinion.']},
  {id:'validation',label:'Final checks',detail:'Checking dates, source references and arithmetic',messages:['Checking the details before handing you the map.','Putting the finishing touches on your next chapter.']},
] as const;

export function stageState(run:Run,id:string):StageState {
  if(run.stage_states?.[id])return run.stage_states[id];
  // Older saved runs have no per-stage completion information.
  if(run.status==='completed')return 'completed';
  if(run.stage===id)return run.status==='failed'?'failed':'running';
  return 'pending';
}

export function progressSummary(run:Run) {
  const completed=STEPS.filter(s=>stageState(run,s.id)==='completed').length;
  const active=STEPS.filter(s=>stageState(run,s.id)==='running');
  const failed=STEPS.filter(s=>stageState(run,s.id)==='failed');
  const busy=run.status==='queued'||run.status==='running';
  const headline=run.status==='completed'?'Your next chapter is ready.':run.status==='failed'?'A pause in the journey.':active.length>1?'Discovering places & the right season':active[0]?.detail||'Getting your journey started';
  return {completed,active,failed,busy,headline};
}

export function elapsedSeconds(run:Run,now:number) {
  const start=Date.parse(run.started_at||'');
  const end=run.finished_at?Date.parse(run.finished_at):now;
  return Number.isFinite(start)&&Number.isFinite(end)?Math.max(0,Math.floor((end-start)/1000)):null;
}

export function clockLabel(seconds:number) {
  return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
}
