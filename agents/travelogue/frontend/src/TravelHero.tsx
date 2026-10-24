import {useState} from 'react';
import type {Country} from './types';

export type PlannerSeed={country:string;interests:string};

export function TravelHero({countries,visited,onPlan,onExplore}:{countries:Country[];visited:number;onPlan:(seed:PlannerSeed)=>void;onExplore:()=>void}) {
  const [prompt,setPrompt]=useState(''),[error,setError]=useState('');
  function start(){
    const text=prompt.trim().toLowerCase();
    const country=text?countries.find(c=>text.includes(c.name.toLowerCase())||c.places.some(p=>text.includes(p.name.toLowerCase()))):countries[0];
    if(!country){setError('This workshop starts with Japan, India, Italy, France, or Thailand. Pick a destination and make it yours.');return;}
    setError('');onPlan({country:country.code,interests:prompt.trim()||'Local food, quiet walks, culture'});
  }
  const suggestions=[{country:'JP',label:'A slower side of Japan',interests:'Quiet neighborhoods, temples, local food; a relaxed pace'},
    {country:'IT',label:'An Italian escape',interests:'Coastal views, local food, slow afternoons'},
    {country:'TH',label:'A little Thai adventure',interests:'Culture, markets, nature, relaxed exploration'}];
  return <section className="travel-hero" aria-labelledby="hero-title">
    <div className="hero-copy"><div className="hero-kicker"><span className="hero-spark" aria-hidden="true">✳</span> LESS ORDINARY. MORE YOU.</div>
      <h1 id="hero-title">Go somewhere<br/>that stays<br/>with <span>you.</span></h1>
      <p className="hero-description">A world to explore. A journey to make your own.<br/>Plan the next adventure and keep the moments that matter.</p>
      <form className="hero-prompt" onSubmit={e=>{e.preventDefault();start();}}><span aria-hidden="true" className="prompt-star">✦</span><label className="sr-only" htmlFor="trip-inspiration">Where would you love to go?</label><input id="trip-inspiration" value={prompt} onChange={e=>{setPrompt(e.target.value);setError('');}} placeholder="Japan, quiet walks, and really good food…" maxLength={1000}/><button type="submit" disabled={!countries.length} aria-label="Start planning this trip"><span aria-hidden="true">↗</span></button></form>
      {error&&<p role="alert" className="hero-error">{error}</p>}
      <div className="hero-suggestions" aria-label="Trip starters">{suggestions.map(s=><button key={s.country} disabled={!countries.length} onClick={()=>onPlan({country:s.country,interests:s.interests})}>{s.label}<span aria-hidden="true">↗</span></button>)}</div>
      <button className="explore-link" onClick={onExplore}>Or unfold your personal atlas <span aria-hidden="true">↓</span></button>
    </div>
    <div className="hero-art" aria-label="Original illustrated travel postcards">
      <div className="hero-dotted-orbit" aria-hidden="true"/>
      <div className="hero-arch"><img src="/art/coast.svg" alt="Illustrated seaside village with colorful houses and blue water"/><div className="arch-caption"><span>TAKE THE SCENIC WAY</span><strong>Somewhere new.<br/>Something unforgettable.</strong></div></div>
      <div className="floating-postcard postcard-japan"><img src="/art/temples.svg" alt="Illustrated pagoda and cherry blossoms"/><div><span>JAPAN</span><strong>A little room to wander.</strong></div></div>
      <div className="floating-postcard postcard-india"><img src="/art/palace.svg" alt="Illustrated Indian palace by a lake"/><div><span>INDIA</span><strong>Find your kind of wonder.</strong></div></div>
      <button className="floating-trip-note" disabled={!countries.length} onClick={()=>onPlan({country:'IT',interests:'Sea views, relaxed local walks, architecture'})}><span className="note-spark" aria-hidden="true">✦</span><span>“Somewhere with sea views<br/>and no need to rush.”<small>Let’s make a plan <span aria-hidden="true">↗</span></small></span></button>
      <div className="hero-stamp"><span>YOUR WORLD</span><strong>{String(visited).padStart(2,'0')}</strong><span>COUNTRIES EXPLORED</span></div>
      <span className="art-caption">A little inspiration, illustrated.</span>
    </div>
  </section>
}
