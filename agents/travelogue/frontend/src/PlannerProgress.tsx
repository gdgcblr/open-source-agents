import {useEffect,useRef,useState} from 'react';
import type {Run} from './types';
import {STEPS,stageState,progressSummary,elapsedSeconds,clockLabel} from './progress';

export function PlannerProgress({run}:{run:Run}) {
  const [now,setNow]=useState(Date.now()),[message,setMessage]=useState(0);
  const panel=useRef<HTMLElement>(null);
  const summary=progressSummary(run);
  const activeId=summary.active.map(s=>s.id).join(',');
  useEffect(()=>{if(!summary.busy)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[summary.busy]);
  useEffect(()=>{setMessage(0);if(!summary.busy)return;const timer=setInterval(()=>setMessage(m=>m+1),6500);return()=>clearInterval(timer);},[activeId,summary.busy]);
  useEffect(()=>{panel.current?.scrollIntoView({block:'nearest',behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});},[run.id]);
  const messages=summary.active[0]?.messages||['Your adventure starts here. Give us a moment to unfold the map.'];
  const elapsed=elapsedSeconds(run,now);
  return <section className={`planner-progress ${summary.busy?'is-working':''} ${run.status==='failed'?'is-failed':''}`} ref={panel} aria-label="Itinerary planning progress">
    <div className="progress-heading"><span className="journey-orbit" aria-hidden="true">{run.status==='completed'?'✓':run.status==='failed'?'!':'✦'}</span><div><p className="eyebrow">{summary.busy?'A GOOD JOURNEY TAKES A LITTLE THOUGHT':run.status==='completed'?'READY FOR YOUR REVIEW':'LET’S FIND THE NEXT STEP'}</p><h3 aria-live="polite" role="status">{summary.headline}</h3></div>{elapsed!==null&&<span className="elapsed-clock" aria-label={`${elapsed} seconds elapsed`}>{clockLabel(elapsed)}</span>}</div>
    <div className={`journey-track ${summary.active.length?'':'preparing'}`} role="progressbar" aria-label="Completed workflow steps" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={summary.completed} aria-valuetext={`${summary.completed} of ${STEPS.length} steps completed${summary.active.length?'; working on '+summary.active.map(s=>s.label).join(' and '):''}`}>
      {STEPS.map(s=><span key={s.id} className={`track-segment ${stageState(run,s.id)}`}/>)}</div>
    <div className="progress-caption"><span>{summary.completed} of {STEPS.length} steps complete</span><span>{summary.busy?'Working, not a time estimate':run.status==='completed'?'Draft ready · Please review travel facts':'No finished itinerary yet'}</span></div>
    {summary.busy&&<><p className="travel-message" key={`${activeId}-${message}`}>{messages[message%messages.length]}</p><p className="wait-message">{run.provider==='demo'?'Walking through the scripted demo — no model is running.':<>Please stay with us — we’re putting your journey together. {elapsed!==null&&elapsed>60?'Still on the journey. Local inference can take several minutes, depending on your computer.':'This can take a few minutes. We’ll update each step as it finishes.'}</>}</p></>}
    {run.status==='failed'&&<p className="wait-message">{summary.failed.length?`Paused during ${summary.failed.map(s=>s.label.toLowerCase()).join(' and ')}. `:''}Your preferences are still in the form below. You can adjust them and try again.</p>}
    <ol className="journey-steps">{STEPS.map((s,i)=>{const state=stageState(run,s.id);return <li key={s.id} className={state} aria-current={state==='running'?'step':undefined}><span className="step-symbol" aria-hidden="true">{state==='completed'?'✓':state==='failed'?'!':i+1}</span><span><strong>{s.label}</strong><small>{state==='running'?'Working on it…':state==='completed'?'Complete':state==='failed'?'Interrupted':'Up next'}</small></span></li>;})}</ol>
  </section>
}
