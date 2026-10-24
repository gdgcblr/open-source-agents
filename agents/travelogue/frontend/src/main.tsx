import React,{useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {WorldMap} from './WorldMap';
import {PlannerProgress} from './PlannerProgress';
import {TravelHero} from './TravelHero';
import type {PlannerSeed} from './TravelHero';
import {memoryStops,memoryThumbnail} from './mapGeometry';
import {api,json,dateLabel} from './types';
import type {Country,Entry,Health,Place,Run} from './types';
import './style.css';
import './experience.css';
import './inspiration.css';
import './journey.css';

function Icon({name,size=20}:{name:string;size?:number}) {
 const paths:Record<string,React.ReactNode>={
  compass:<><circle cx="12" cy="12" r="9"/><path d="m16 8-3 5-5 3 3-5Z"/></>,
  globe:<><circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 7h14M5 17h14"/></>,
  book:<><path d="M4 4h6l2 2 2-2h6v15h-6l-2 2-2-2H4Z"/><path d="M12 6v15"/></>,
  plane:<><path d="m21 3-7 18-3-8-8-3Z"/><path d="m11 13 5-5"/></>,
  bookmark:<path d="M6 3h12v18l-6-4-6 4Z"/>,
  plus:<path d="M12 5v14M5 12h14"/>,
  search:<><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
  arrow:<path d="M4 12h16m-6-6 6 6-6 6"/>,
  pin:<><path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/></>,
  close:<path d="m6 6 12 12M6 18 18 6"/>,
  lock:<><rect x="6" y="10" width="12" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></>,
  spark:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/><path d="m20 2 .5 1.5L22 4l-1.5.5L20 6l-.5-1.5L18 4l1.5-.5Z"/></>,
  check:<path d="m5 12 4 4L19 6"/>,
  camera:<><path d="M3 7h5l2-3h4l2 3h5v13H3Z"/><circle cx="12" cy="13" r="4"/></>
 };
 return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]||paths.compass}</svg>
}

function Modal({children,title,onClose,wide=false}:{children:React.ReactNode;title:string;onClose:()=>void;wide?:boolean}) {
 const ref=useRef<HTMLDialogElement>(null);
 useEffect(()=>{const d=ref.current;d?.showModal();return()=>{d?.close();}},[]);
 return <dialog ref={ref} className={`modal ${wide?'wide':''}`} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===e.currentTarget)onClose();}} aria-label={title}><div className="modal-top"><span className="eyebrow">{title}</span><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close"/></button></div>{children}</dialog>
}

function EntryEditor({entry,countries,onClose,onSaved}:{entry:Entry|null;countries:Country[];onClose:()=>void;onSaved:()=>Promise<void>}) {
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[savedId,setSavedId]=useState(entry?.id||'');
 const files=useRef<HTMLInputElement>(null);
 async function submit(e:React.FormEvent<HTMLFormElement>) {
  e.preventDefault();setBusy(true);setError('');const form=new FormData(e.currentTarget);
  try {
   const payload={place_id:form.get('place_id'),title:form.get('title'),visited_on:form.get('visited_on'),body:form.get('body'),tags:form.get('tags'),published:false};
   const result=await api<Entry>(savedId?`/entries/${savedId}`:'/entries',json(payload,savedId?'PUT':'POST'));setSavedId(result.id);
   for(const file of Array.from(files.current?.files||[])){const body=new FormData();body.append('file',file);await api(`/entries/${result.id}/media`,{method:'POST',body});}
   await onSaved();onClose();
  } catch(e){await onSaved();setError((e as Error).message+' Your saved text is preserved; retry after correcting the attachment.');}
  finally{setBusy(false);}
 }
 return <Modal title={entry?'EDIT A MEMORY':'A NEW CHAPTER'} onClose={onClose}><h2>{entry?'Keep the details.':'Some days deserve a page.'}</h2><p className="muted">The little things are the big things. Make a note of yours.</p><form onSubmit={submit} className="form-grid">
  <label>Where did you go?<select name="place_id" defaultValue={entry?.place_id||'kyoto'}>{countries.map(c=><optgroup label={c.name} key={c.code}>{c.places.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</optgroup>)}</select></label>
  <label>When?<input type="date" name="visited_on" required max={new Date().toLocaleDateString('en-CA')} defaultValue={entry?.visited_on||new Date().toLocaleDateString('en-CA')}/></label>
  <label className="full">Give this memory a name<input name="title" required maxLength={160} defaultValue={entry?.title} placeholder="A morning I want to remember"/></label>
  <label className="full">Your story<textarea name="body" rows={6} maxLength={20000} defaultValue={entry?.body} placeholder="What did it feel like to be there?"/></label>
  <label className="full">Tags<input name="tags" maxLength={200} defaultValue={entry?.tags} placeholder="Slow travel, Food, Little moments"/></label>
  <label className="full upload-box"><Icon name="camera"/>Photos & short videos<input type="file" multiple ref={files} accept="image/jpeg,image/png,image/webp,video/mp4,video/webm"/><small>Images ≤10 MB · Videos ≤25 MB and 30 seconds. FFprobe required on host.</small></label>
  <p className="privacy full"><Icon name="lock" size={14}/>Private on this computer. Public sharing is not enabled.</p>
  {error&&<p role="alert" className="error full">{error}</p>}<button className="button primary full" disabled={busy}>{busy?'Saving your memory…':entry?'Save changes':'Keep this memory'}<Icon name="arrow" size={18}/></button>
 </form></Modal>
}

function JournalDetail({entry,place,onClose,onEdit,onDelete,onRefresh}:{entry:Entry;place:Place;onClose:()=>void;onEdit:()=>void;onDelete:()=>void;onRefresh:()=>Promise<void>}) {
 const [error,setError]=useState('');
 return <Modal title="FROM YOUR TRAVEL JOURNAL" wide onClose={onClose}><img className="article-image" src={place.image} alt={`Illustration inspired by ${place.name}`}/><div className="article-body"><div className="eyebrow">{place.name.toUpperCase()} · {dateLabel(entry.visited_on)}</div><h2>{entry.title}</h2><p className="privacy"><Icon name="lock" size={14}/>Private memory · Sample stories are fictional</p>{entry.body?entry.body.split('\n').map((p,i)=><p className="story" key={i}>{p}</p>):<p className="muted">A place recorded, a story still to come.</p>}<div className="tags">{entry.tags.split(',').filter(Boolean).map(t=><span key={t}>{t.trim()}</span>)}</div>
 <div className="media-grid">{entry.media.map(m=><figure key={m.id}>{m.mime.startsWith('video')?<video controls src={`/api/media/${m.id}`} preload="metadata"/>:<img src={`/api/media/${m.id}`} alt={m.filename}/>}<figcaption>{m.filename}<button className="text-button" onClick={async()=>{try{await api(`/media/${m.id}`,{method:'DELETE'});await onRefresh();}catch(e){setError((e as Error).message);}}}>Remove attachment</button></figcaption></figure>)}</div>
 {error&&<p className="error" role="alert">{error}</p>}<div className="actions"><button className="button" onClick={onEdit}>Edit memory</button><button className="text-button danger" onClick={onDelete}>Delete memory</button></div></div></Modal>
}

function Planner({countries,onClose,onSaved,existing,seed}:{countries:Country[];onClose:()=>void;onSaved:()=>void;existing:Run|null;seed:PlannerSeed}) {
 const [run,setRun]=useState<Run|null>(existing),[error,setError]=useState(''),[busy,setBusy]=useState(false),[saved,setSaved]=useState(false),[status,setStatus]=useState('');
 const timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 useEffect(()=>{api<{message:string}>('/model/status').then(d=>setStatus(d.message)).catch(()=>{});return()=>{if(timer.current)clearTimeout(timer.current);};},[]);
 useEffect(()=>{if(!run||!['queued','running'].includes(run.status))return;timer.current=setTimeout(()=>api<Run>(`/planner/runs/${run.id}`).then(next=>{setRun(next);setError('');}).catch(e=>{setError('Connection interrupted — checking again. '+e.message);setRun(previous=>previous?{...previous}:previous);}),1200);return()=>{if(timer.current)clearTimeout(timer.current);};},[run]);
 async function submit(e:React.FormEvent<HTMLFormElement>){e.preventDefault();setError('');setBusy(true);setSaved(false);const f=new FormData(e.currentTarget);try{setRun(await api<Run>('/planner/runs',json({country:f.get('country'),start_date:f.get('start_date'),end_date:f.get('end_date'),travelers:Number(f.get('travelers')),budget:f.get('budget'),currency:f.get('currency'),interests:f.get('interests'),pace:f.get('pace')})));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const running=run&&['queued','running'].includes(run.status);
 return <Modal title="THE NEXT CHAPTER" wide onClose={onClose}><div className="planner-heading"><div className="plan-icon"><Icon name="spark" size={26}/></div><h2>Good trips start with a little curiosity.</h2><p className="muted">Four specialists. One itinerary. A little more room to wander.</p><p className="model-status">{status}</p></div>
 {run&&<PlannerProgress run={run}/>}
 {!existing&&<form className="form-grid planner-form" onSubmit={submit}>
  <label>Country<select name="country" defaultValue={seed.country}>{countries.map(c=><option key={c.code} value={c.code}>{c.name}</option>)}</select></label><label>Travel pace<select name="pace"><option value="relaxed">Slow & unhurried</option><option value="balanced">A bit of everything</option><option value="active">Make the most of it</option></select></label>
  <label>Start date<input name="start_date" type="date" required defaultValue="2026-11-10"/></label><label>End date<input name="end_date" type="date" required defaultValue="2026-11-14"/></label>
  <label>Travelers<input name="travelers" type="number" min={1} max={10} defaultValue={2} required/></label><label>Total budget<input name="budget" type="number" min="0.01" step="0.01" max="100000000" defaultValue={100000} required/></label>
  <label>Currency<select name="currency">{['INR','USD','EUR','JPY','THB'].map(c=><option key={c}>{c}</option>)}</select></label><label>Your interests<input name="interests" required maxLength={1000} defaultValue={seed.interests}/></label>
  <button className="button primary full" disabled={busy||!!running}>{busy||running?'Putting your journey together…':'Plan my next chapter'}<Icon name="spark" size={18}/></button>
 </form>}
 {(error||run?.error)&&<p role="alert" className="error">{error||run?.error}</p>}

 {run?.result&&<section className="itinerary"><div className="itinerary-head"><div><p className="eyebrow">{run.result.provider==='demo'?'SCRIPTED DEMO · NO MODEL RAN':`LOCAL INFERENCE · ${run.result.model}`}</p><h3>{run.result.itinerary.title}</h3></div><button className="button" disabled={saved} onClick={async()=>{try{await api(`/plans/${run.id}`,json(run.result?.itinerary));setSaved(true);onSaved();}catch(e){setError((e as Error).message);}}}>{saved?'Saved':'Save itinerary'}<Icon name="bookmark" size={16}/></button></div>
 <p className="muted">Activity estimates: {run.result.itinerary.currency} {Number(run.result.estimated_total).toLocaleString()} · {run.result.itinerary.travelers} travelers</p>
 <div className="notice">{run.result.itinerary.warnings.map((w,i)=><p key={i}>{w}</p>)}<p>Structural checks passed. Factual correctness has not been evaluated.</p></div>
 {run.result.itinerary.days.map((day,i)=><div className="plan-day" key={day.date}><div className="day-index">{String(i+1).padStart(2,'0')}</div><div><p className="eyebrow">{dateLabel(day.date)}</p>{day.activities.map((a,j)=><div key={j}><input className="activity-title" aria-label={`Day ${i+1} activity ${j+1} title`} value={a.title} maxLength={200} onChange={e=>{const next=structuredClone(run);next.result!.itinerary.days[i].activities[j].title=e.target.value;setRun(next);setSaved(false);}}/><textarea className="activity-note" aria-label={`Day ${i+1} activity ${j+1} notes`} value={a.note} maxLength={1500} rows={3} onChange={e=>{const next=structuredClone(run);next.result!.itinerary.days[i].activities[j].note=e.target.value;setRun(next);setSaved(false);}}/><small>{run.result?.itinerary.currency} {a.estimate} · {a.source_ids.map(id=>{const source=run.result?.sources.find(s=>s.id===id);return source?<a href={source.url} target="_blank" rel="noreferrer" key={id}>{source.title} ↗ </a>:null;})}</small></div>)}</div></div>)}</section>}
 </Modal>
}

function App() {
 const [theme,setTheme]=useState<'light'|'dark'>(()=>{try{return localStorage.getItem('travelogue-theme')==='dark'?'dark':'light';}catch{return 'light';}});
 const [plannerSeed,setPlannerSeed]=useState<PlannerSeed>({country:'JP',interests:'Local food, quiet walks, culture'});
 useEffect(()=>{document.documentElement.dataset.theme=theme;document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme==='light'?'#fafaf7':'#090d14');try{localStorage.setItem('travelogue-theme',theme);}catch{}},[theme]);
 const [countries,setCountries]=useState<Country[]>([]),[entries,setEntries]=useState<Entry[]>([]),[health,setHealth]=useState<Health|null>(null),[loadError,setLoadError]=useState('');
 const [nav,setNav]=useState('atlas'),[selected,setSelected]=useState('FR'),[selectedName,setSelectedName]=useState('France'),[search,setSearch]=useState(''),[filter,setFilter]=useState('all');
 const [activeStop,setActiveStop]=useState(''),[focusRequest,setFocusRequest]=useState(0);
 const [editor,setEditor]=useState<Entry|null|undefined>(undefined),[detailId,setDetailId]=useState(''),[planner,setPlanner]=useState(false),[existingPlan,setExistingPlan]=useState<Run|null>(null),[plans,setPlans]=useState<Run[]>([]),[toast,setToast]=useState('');
 async function refresh(){setEntries(await api<Entry[]>('/entries'));setPlans(await api<Run[]>('/plans'));}
 async function load(){setLoadError('');try{const [c,e,h,p]=await Promise.all([api<{countries:Country[]}>('/catalog'),api<Entry[]>('/entries'),api<Health>('/health'),api<Run[]>('/plans')]);setCountries(c.countries);setEntries(e);setHealth(h);setPlans(p);}catch(e){setLoadError((e as Error).message);}}
 useEffect(()=>{void load();},[]);
 useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(''),5000);return()=>clearTimeout(t);},[toast]);
 const places=countries.flatMap(c=>c.places),visited=new Set(entries.map(e=>e.country)),country=countries.find(c=>c.code===selected),countryEntries=entries.filter(e=>e.country===selected);
 const stops=memoryStops(entries,places);
 const detail=entries.find(e=>e.id===detailId),detailPlace=places.find(p=>p.id===detail?.place_id);
 const memories=entries.filter(e=>{const p=places.find(p=>p.id===e.place_id);return (filter==='all'||e.country===filter)&&(!search||[e.title,p?.name,countries.find(c=>c.code===e.country)?.name].join(' ').toLowerCase().includes(search.toLowerCase()));});
 function focusMemory(id:string){setActiveStop(id);setFocusRequest(n=>n+1);}
 function selectCountry(code:string,name?:string){setSelected(code);setSelectedName(name||countries.find(c=>c.code===code)?.name||code);}
 function openPlanner(run:Run|null=null,seed?:PlannerSeed){setPlannerSeed(seed||{country:countries.some(c=>c.code===selected)?selected:'JP',interests:'Local food, quiet walks, culture'});setExistingPlan(run);setPlanner(true);}
 function goTop(){window.scrollTo({top:0,behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
 function exploreAtlas(){document.getElementById('personal-atlas')?.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});}
 return <><a className="skip-link" href="#main">Skip to content</a>
 <header className="site-header"><div className="header-inner"><a className="brand" href="#" onClick={e=>{e.preventDefault();setNav('atlas');goTop();}}><span className="brand-mark"><Icon name="compass" size={30}/></span><span>travelogue<span className="brand-period">.</span></span></a>
 <nav className="main-nav" aria-label="Main navigation">{[['atlas','Discover'],['journal','My journal'],['saved','Saved trips']].map(([key,label])=><button key={key} className={nav===key?'active':''} onClick={()=>{setNav(key);goTop();}}>{label}{key==='saved'&&plans.length>0&&<span>{plans.length}</span>}</button>)}<button onClick={()=>openPlanner()}>Plan a trip <span aria-hidden="true">↗</span></button></nav>
 <div className="header-actions"><button className="theme-toggle" onClick={()=>setTheme(t=>t==='light'?'dark':'light')} aria-label={`Switch to ${theme==='light'?'dark':'light'} mode`} title={`Switch to ${theme==='light'?'dark':'light'} mode`}><span aria-hidden="true">{theme==='light'?'☾':'☀'}</span></button><button className="button header-memory" disabled={!countries.length} onClick={()=>setEditor(null)}><Icon name="plus" size={16}/>Add a memory</button></div></div></header>
 <div className="app-shell">
 <main id="main">{nav==='atlas'?<TravelHero countries={countries} visited={visited.size} onPlan={seed=>openPlanner(null,seed)} onExplore={exploreAtlas}/>:<section className="page-intro"><div><p className="eyebrow">YOUR WORLD, IN YOUR OWN WORDS</p><h1>{nav==='journal'?<>Some days stay <em>with you.</em></>:<>Good things <em>ahead.</em></>}</h1><p className="intro-copy">{nav==='saved'?'A little inspiration for wherever life takes you next.':'Your places. Your people. The stories you’ll come back to.'}</p></div><button className="button primary" onClick={()=>nav==='saved'?openPlanner():setEditor(null)}><Icon name={nav==='saved'?'plane':'plus'} size={17}/>{nav==='saved'?'Plan a trip':'Add a memory'}</button></section>}
 <div className="workspace-status"><span className="workspace-edition">A PERSONAL ATLAS, A TRAVEL JOURNAL, A LITTLE POSSIBILITY.</span><span className="demo-badge"><i/>{health?.provider==='ollama'?'Local Gemma · Demo storage':'Local demo · Scripted planner'}</span></div>
 {loadError&&<div className="notice error" role="alert">Could not connect to the local backend. {loadError}<button className="text-button" onClick={()=>void load()}>Try again</button></div>}
 <section className="stats" aria-label="Your travel statistics"><div><span className="stat-icon"><Icon name="globe"/></span><strong>{String(visited.size).padStart(2,'0')}</strong><span>countries explored<small>A little more of the world</small></span></div><div><span className="stat-icon"><Icon name="pin"/></span><strong>{String(new Set(entries.map(e=>e.place_id)).size).padStart(2,'0')}</strong><span>places close to heart<small>Every place, a new perspective</small></span></div><div><span className="stat-icon"><Icon name="book"/></span><strong>{String(entries.length).padStart(2,'0')}</strong><span>memories collected<small>The details worth keeping</small></span></div><div className="stat-quote">“Not all those who wander<br/><em>are lost.</em>”<small>J. R. R. TOLKIEN</small></div></section>
 {nav==='atlas'&&<section className="atlas-section" id="personal-atlas"><div className="section-heading"><div><p className="eyebrow">A WORLD OF POSSIBILITIES</p><h2>Your personal atlas<span className="heading-dot">.</span></h2></div><label className="search-box"><Icon name="search" size={16}/><input aria-label="Search countries and memories" placeholder="Find a country or a memory…" value={search} onChange={e=>setSearch(e.target.value)}/></label></div><div className="atlas-card"><WorldMap countries={countries} entries={entries} selected={selected} onSelect={selectCountry} onOpenMemory={setDetailId} focusedEntryId={activeStop} focusRequest={focusRequest} onFocusMemory={focusMemory} search={search}/><aside className="country-panel journey-sidebar"><div className="journey-sidebar-intro"><span className="eyebrow">THE PLACES THAT BECOME YOUR STORY</span><h3>Your travel<br/>journal<span>.</span></h3><p>{stops.length} memories · {visited.size} countries · Your own pace</p></div><ol className="sidebar-stops">{stops.map(({entry,place},index)=><li key={entry.id} className={activeStop===entry.id?'active':''}><button className="stop-select" onClick={()=>{focusMemory(entry.id);selectCountry(place.country);}} aria-label={`Show step ${index+1}, ${place.name}, on the map`} aria-pressed={activeStop===entry.id}><span className="stop-number">{index+1}</span><img src={memoryThumbnail(entry,place)} alt=""/><span><time dateTime={entry.visited_on}>{dateLabel(entry.visited_on)}</time><strong>{place.name}</strong><small>{entry.title}</small></span></button><button className="stop-read" aria-label={`Read ${entry.title}`} onClick={()=>setDetailId(entry.id)}>↗</button></li>)}</ol>{!stops.length&&<p className="muted">Add your first memory to start a trail.</p>}<div className="sidebar-discovery-label">A LITTLE MORE TO EXPLORE</div><div className="country-panel-top"><span className="eyebrow">{visited.has(selected)?'A CHAPTER YOU’VE LIVED':'YOUR NEXT CHAPTER?'}</span><span className="country-code">{selected}</span></div><h3>{country?.name||selectedName}</h3><p className="muted">{country?.subtitle||'The next story is yours to discover.'}</p><label className="sr-only" htmlFor="country-select">Explore a curated country</label><select id="country-select" value={country?selected:''} onChange={e=>selectCountry(e.target.value)}><option value="" disabled>Select a curated country</option>{countries.map(c=><option value={c.code} key={c.code}>{c.name}{visited.has(c.code)?' · Visited':''}</option>)}</select>
 {countryEntries.length>0?<div className="country-places">{countryEntries.map(e=>{const p=places.find(p=>p.id===e.place_id);return <button className="mini-place" key={e.id} onClick={()=>setDetailId(e.id)}><img src={p?.image} alt=""/><span><strong>{p?.name}</strong><small>{e.title}</small></span><Icon name="arrow" size={15}/></button>})}</div>:country?<div className="country-places">{country.places.map(p=><a className="mini-place" key={p.id} href={p.source} target="_blank" rel="noreferrer"><img src={p.image} alt=""/><span><strong>{p.name}</strong><small>{p.season}</small></span><span aria-hidden="true">↗</span></a>)}</div>:<div className="empty-small"><Icon name="compass" size={30}/><p>Discovery cards haven’t been curated here yet. Choose one of the five workshop countries.</p></div>}
 <p className="fixture-note">Illustrated thumbnails · Seasonal guidance is unverified. Links open official tourism sites.</p><button className="button subtle full-width" disabled={!country} onClick={()=>openPlanner()}>Imagine a journey here<Icon name="arrow" size={16}/></button></aside></div></section>}
 {nav!=='saved'?<section className="memories-section"><div className="section-heading"><div><p className="eyebrow">LITTLE MOMENTS, LASTING STORIES</p><h2>The travel journal<span className="heading-dot">.</span></h2></div><span className="handwritten">a few pages from your life ↙</span></div><div className="journal-toolbar"><div className="filter-tabs"><button className={filter==='all'?'active':''} onClick={()=>setFilter('all')}>All memories <span>{entries.length}</span></button>{countries.filter(c=>visited.has(c.code)).map(c=><button key={c.code} className={filter===c.code?'active':''} onClick={()=>setFilter(c.code)}>{c.name}</button>)}</div><span className="sort-label">Newest stories first ↓</span></div>
 <div className={`memory-grid ${nav==='journal'?'timeline-view':''}`}>{memories.map((e,i)=>{const p=places.find(p=>p.id===e.place_id);return <article className="memory-card" data-date={dateLabel(e.visited_on)} key={e.id} style={{animationDelay:`${i*70}ms`}}><button className="memory-open" onClick={()=>setDetailId(e.id)} aria-label={`Read ${e.title}`}><div className="memory-image"><img src={p?.image} alt={`Illustration inspired by ${p?.name}`} loading="lazy"/><span className="location-tag"><Icon name="pin" size={12}/>{p?.name}, {countries.find(c=>c.code===e.country)?.name}</span><span className="image-number">{String(memories.length-i).padStart(2,'0')}</span></div><div className="memory-content"><div className="memory-meta"><time dateTime={e.visited_on}>{dateLabel(e.visited_on)}</time><Icon name="lock" size={12}/></div><h3>{e.title}</h3><p>{e.body||'A place recorded, a story still to come.'}</p><div className="card-bottom"><span>{e.tags.split(',')[0]||'A little adventure'}{e.media.length>0?` · ${e.media.length} attachments`:''}</span><Icon name="arrow" size={18}/></div></div></button></article>})}<button className="new-memory-card" disabled={!countries.length} onClick={()=>setEditor(null)}><span className="dashed-circle"><Icon name="plus" size={25}/></span><h3>There’s always<br/>another story.</h3><p>Add a place. Keep a moment.<br/>Make it part of your world.</p><span className="text-link">Write your next page <Icon name="arrow" size={16}/></span></button></div>{!memories.length&&<p className="muted">No memories match this view. Try another country or add your first memory.</p>}</section>:<section className="saved-section">{plans.length?plans.map(p=><button className="saved-card" key={p.id} onClick={()=>openPlanner(p)}><Icon name="bookmark" size={24}/><div><h3>{p.result?.itinerary.title}</h3><p>{p.result?.provider==='demo'?'Scripted demo':'Local Gemma'} · {p.result?.itinerary.days.length} days</p></div><Icon name="arrow"/></button>):<div className="empty-state"><Icon name="plane" size={40}/><h2>A blank page. A world of possibility.</h2><p>Create a trip plan and save it here for later.</p><button className="button primary" onClick={()=>openPlanner()}>Plan a journey<Icon name="arrow" size={16}/></button></div>}</section>}
 <footer className="page-footer"><span>Made for the places that become part of you.</span><span>TRAVELOGUE <span className="tiny-star">✳</span> WORKSHOP EDITION</span></footer></main></div>
 {editor!==undefined&&<EntryEditor entry={editor} countries={countries} onClose={()=>setEditor(undefined)} onSaved={refresh}/>}
 {detail&&detailPlace&&editor===undefined&&<JournalDetail entry={detail} place={detailPlace} onClose={()=>setDetailId('')} onRefresh={refresh} onEdit={()=>{setEditor(detail);setDetailId('');}} onDelete={async()=>{if(!window.confirm('Delete this memory and its attachments?'))return;try{await api(`/entries/${detail.id}`,{method:'DELETE'});setDetailId('');await refresh();setToast('Memory deleted.');}catch(e){setToast((e as Error).message);}}}/>}
 {planner&&<Planner countries={countries} seed={plannerSeed} existing={existingPlan} onClose={()=>setPlanner(false)} onSaved={()=>{void refresh();setToast('Itinerary saved on this computer.');}}/>}
 {toast&&<div className="toast" role="status">{toast}</div>}
 </>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
