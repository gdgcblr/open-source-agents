import {useEffect,useId,useMemo,useRef,useState} from 'react';
import type {Country,Entry,Feature,Place} from './types';
import {dateLabel} from './types';
import {countryPath,popupPosition,project,WORLD_VIEW,constrainView,zoomView,fitPlaces,memoryStops,memoryTrail,memoryThumbnail,riverPath} from './mapGeometry';
import type {MapView} from './mapGeometry';
import type {PointerEvent as MapPointerEvent} from 'react';

type Geography={lakes:{geometry:Feature['geometry']}[];rivers:{geometry:{coordinates:number[][]}}[];labels:{code3:string;lon:number;lat:number;rank:number}[]};

type Preview={kind:'country'|'place';id:string;name:string;x:number;y:number;pinned:boolean};
type Props={countries:Country[];entries:Entry[];selected:string;onSelect:(code:string,name?:string)=>void;onOpenMemory:(id:string)=>void;focusedEntryId:string;focusRequest:number;onFocusMemory:(id:string)=>void;search:string};

function ExpandIcon({close=false}:{close?:boolean}) {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">{close?<path d="m6 6 12 12M6 18 18 6"/>:<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>}</svg>
}

export function WorldMap({countries,entries,selected,onSelect,onOpenMemory,focusedEntryId,focusRequest,onFocusMemory,search}:Props) {
  const [features,setFeatures]=useState<Feature[]>([]),[error,setError]=useState(false),[hover,setHover]=useState('');
  const [geography,setGeography]=useState<Geography|null>(null);
  const [expanded,setExpanded]=useState(false),[popouts,setPopouts]=useState(true),[preview,setPreview]=useState<Preview|null>(null);
  const [view,setView]=useState<MapView>({...WORLD_VIEW}),[showTrail,setShowTrail]=useState(true),[dragging,setDragging]=useState(false),[showAttractions,setShowAttractions]=useState(false);
  const svg=useRef<SVGSVGElement>(null),initialFit=useRef(false);
  const drag=useRef<{active:boolean;moved:boolean;id:number;x:number;y:number;view:MapView}|null>(null);
  const mapRoot=useRef<HTMLDivElement>(null),dialog=useRef<HTMLDialogElement>(null),expandButton=useRef<HTMLButtonElement>(null);
  const closeTimer=useRef<ReturnType<typeof setTimeout>|null>(null),nativeFullscreen=useRef(false);
  const popout=useRef<HTMLElement>(null),trigger=useRef<Element|null>(null),skipFocus=useRef(false);
  const gradientId=useId().replaceAll(':','');
  useEffect(()=>{const abort=new AbortController();fetch('/world.json',{signal:abort.signal}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>setFeatures(d.features)).catch(e=>{if(e.name!=='AbortError')setError(true);});return()=>abort.abort();},[]);
  useEffect(()=>{const abort=new AbortController();fetch('/geography.json',{signal:abort.signal}).then(r=>{if(!r.ok)throw Error();return r.json();}).then(setGeography).catch(()=>{});return()=>abort.abort();},[]);
  useEffect(()=>()=>{if(closeTimer.current)clearTimeout(closeTimer.current);},[]);
  const paths=useMemo(()=>features.filter(f=>f.properties.code!=='AQ').map(f=>({...f,d:countryPath(f)})),[features]);
  const lakes=useMemo(()=>geography?.lakes.map(countryPath)||[],[geography]);
  const rivers=useMemo(()=>geography?.rivers.map(r=>riverPath(r.geometry.coordinates))||[],[geography]);
  const countryNames=useMemo(()=>new Map(features.map(f=>[f.properties.code3,f.properties.name])),[features]);
  const places=countries.flatMap(c=>c.places),visited=new Set(entries.map(e=>e.country)),visitedPlaces=new Set(entries.map(e=>e.place_id));
  const markers=places.filter(p=>visitedPlaces.has(p.id)||(showAttractions&&p.country===selected));
  const stops=memoryStops(entries,places),trail=memoryTrail(stops),zoom=1000/view.width;
  const activeStop=stops.find(s=>s.entry.id===focusedEntryId);
  useEffect(()=>{if(!initialFit.current&&stops.length){initialFit.current=true;setView(fitPlaces(stops.map(s=>s.place)));}},[entries,countries]);
  useEffect(()=>{const stop=memoryStops(entries,countries.flatMap(c=>c.places)).find(s=>s.entry.id===focusedEntryId);if(stop)focusPlace(stop.place);},[focusedEntryId,focusRequest,entries,countries]);
  useEffect(()=>{
    const element=svg.current;if(!element)return;
    function wheel(event:WheelEvent){
      if(!event.ctrlKey&&!event.metaKey)return;
      event.preventDefault();setPreview(null);
      const matrix=element!.getScreenCTM();if(!matrix)return;
      const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
      setView(current=>zoomView(current,event.deltaY<0?1.2:1/1.2,[point.x,point.y]));
    }
    element.addEventListener('wheel',wheel,{passive:false});
    return()=>element.removeEventListener('wheel',wheel);
  },[expanded,error,features.length]);
  function focusPlace(place:Place){
    setShowAttractions(false);setPreview(null);setView(current=>{const fitted=fitPlaces([place]),width=Math.min(current.width,fitted.width),[x,y]=project(place.lon,place.lat);return constrainView({x:x-width/2,y:y-width*470/2000,width,height:width*470/1000});});
  }
  function focusStop(id:string){const stop=stops.find(s=>s.entry.id===id);if(!stop)return;onSelect(stop.place.country);onFocusMemory(id);focusPlace(stop.place);}
  function zoomMap(factor:number){setPreview(null);setView(current=>zoomView(current,factor));}
  function startPan(event:MapPointerEvent<SVGSVGElement>){
    if(event.button!==0||!event.isPrimary)return;
    drag.current={active:true,moved:false,id:event.pointerId,x:event.clientX,y:event.clientY,view:{...view}};
  }
  function pan(event:MapPointerEvent<SVGSVGElement>){
    const gesture=drag.current;if(!gesture?.active||gesture.id!==event.pointerId)return;
    const dx=event.clientX-gesture.x,dy=event.clientY-gesture.y;
    if(!gesture.moved&&Math.hypot(dx,dy)<5)return;
    if(!gesture.moved){event.currentTarget.setPointerCapture(event.pointerId);gesture.moved=true;setPreview(null);setDragging(true);}
    const matrix=event.currentTarget.getScreenCTM();const scale=matrix?.a||1;
    setView(constrainView({...gesture.view,x:gesture.view.x-dx/scale,y:gesture.view.y-dy/scale}));
  }
  function endPan(event:MapPointerEvent<SVGSVGElement>){
    if(drag.current?.id!==event.pointerId)return;
    drag.current.active=false;setDragging(false);
    if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
  }


  function cancelClose(){if(closeTimer.current)clearTimeout(closeTimer.current);}
  function scheduleClose(){cancelClose();closeTimer.current=setTimeout(()=>setPreview(p=>p?.pinned?p:null),260);}
  function show(kind:Preview['kind'],id:string,name:string,target:Element,x?:number,y?:number,pinned=false) {
    if(drag.current?.active&&drag.current.moved)return;
    cancelClose();setHover(name);
    if(!popouts)return;
    if(preview?.pinned&&!pinned)return;
    trigger.current=target;
    const root=mapRoot.current?.getBoundingClientRect(),bounds=target.getBoundingClientRect();
    if(!root)return;
    setPreview({kind,id,name,pinned,x:(x||bounds.left+bounds.width/2)-root.left,y:(y||bounds.top+bounds.height/2)-root.top});
    if(pinned)requestAnimationFrame(()=>popout.current?.focus());
  }
  function dismissPreview(){
    cancelClose();setPreview(null);
    const target=trigger.current;
    if(target&&'focus' in target&&typeof target.focus==='function'){skipFocus.current=true;target.focus();}
  }
  function closeExpanded(){
    nativeFullscreen.current=false;
    if(document.fullscreenElement===dialog.current)void document.exitFullscreen().catch(()=>{});
    dialog.current?.close();setExpanded(false);setPreview(null);
    requestAnimationFrame(()=>expandButton.current?.focus());
  }
  useEffect(()=>{function change(){if(nativeFullscreen.current&&!document.fullscreenElement)closeExpanded();}document.addEventListener('fullscreenchange',change);return()=>document.removeEventListener('fullscreenchange',change);},[]);
  function openExpanded(){
    setPreview(null);setExpanded(true);dialog.current?.showModal();
    if(dialog.current?.requestFullscreen)void dialog.current.requestFullscreen().then(()=>{nativeFullscreen.current=true;}).catch(()=>{});
  }
  function openMemory(id:string){if(expanded)closeExpanded();setPreview(null);onOpenMemory(id);}
  const previewPlace=preview?.kind==='place'?places.find(p=>p.id===preview.id):undefined;
  const previewCountry=preview?.kind==='country'?countries.find(c=>c.code===preview.id):countries.find(c=>c.code===previewPlace?.country);
  const previewEntries=entries.filter(e=>previewPlace?e.place_id===previewPlace.id:e.country===preview?.id);
  const previewPlaces=previewPlace?[previewPlace]:previewCountry?.places||[];
  const position=preview&&mapRoot.current?popupPosition(mapRoot.current.clientWidth,mapRoot.current.clientHeight,preview.x,preview.y):undefined;

  const stage=<div className={`world-wrap journal-map ${expanded?'expanded-map':''} ${dragging?'is-dragging':''}`} ref={mapRoot} onMouseLeave={()=>{setHover('');scheduleClose();}} onKeyDown={e=>{if(e.key==='Escape'&&preview){e.preventDefault();e.stopPropagation();dismissPreview();}}}>
    <div className="map-toolbar"><span className="map-caption"><i className="live-dot"/>YOUR WORLD, STEP BY STEP</span><div className="map-controls"><button className={`map-control ${showTrail?'enabled':''}`} aria-pressed={showTrail} onClick={()=>setShowTrail(!showTrail)}><span aria-hidden="true">⌁</span>Memory trail</button><button className={`map-control ${popouts?'enabled':''}`} aria-pressed={popouts} onClick={()=>{setPopouts(!popouts);setPreview(null);}}><span aria-hidden="true">◈</span>Pop-out previews</button><button ref={expanded?undefined:expandButton} className="map-control" aria-label={expanded?'Exit fullscreen map':'Open fullscreen map'} onClick={expanded?closeExpanded:openExpanded}><ExpandIcon close={expanded}/>{expanded?'Exit full screen':'Full screen'}</button></div></div>
    {expanded&&<div className="expanded-map-heading"><span className="eyebrow">THE JOURNEY IS IN THE LITTLE MOMENTS</span><h2>Your world. <em>One step at a time.</em></h2><p>Drag to explore. Zoom into a memory. Follow the stories that brought you here.</p></div>}
    {error?<p role="alert">The bundled map could not load. Use the country selector below.</p>:<svg ref={svg} viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`} className="world-map" onPointerDown={startPan} onPointerMove={pan} onPointerUp={endPan} onPointerCancel={endPan} role="group" aria-label="Interactive world map. Hover, focus, or select a country or place to explore." onMouseLeave={scheduleClose}>
      <defs><radialGradient id={gradientId}><stop stopColor="#365965"/><stop offset="1" stopColor="#1d3642"/></radialGradient></defs>
      <rect width="1000" height="470" fill={`url(#${gradientId})`} onClick={()=>setPreview(null)}/>
      <g className="graticule">{[-60,-30,0,30,60].map(lat=><path key={lat} d={`M0 ${project(0,lat)[1]} H1000`}/>)}{[-150,-90,-30,30,90,150].map(lon=><path key={lon} d={`M${project(lon,0)[0]} 0 V470`}/>)}</g>
      {paths.map(f=>{const {code,name}=f.properties;const matches=!search||name.toLowerCase().includes(search.toLowerCase());return <path key={f.properties.code3} d={f.d} tabIndex={0} role="button" aria-label={`${name}, ${visited.has(code)?'visited':'not visited'}`} aria-pressed={selected===code} className={`country ${visited.has(code)?'visited':''} ${selected===code?'selected':''} ${matches?'':'dimmed'}`}
        onMouseEnter={e=>{if(drag.current?.active&&drag.current.moved)return;setShowAttractions(true);onSelect(code,name);show('country',code,name,e.currentTarget,e.clientX,e.clientY);}} onMouseLeave={scheduleClose}
        onFocus={e=>{if(skipFocus.current){skipFocus.current=false;return;}setShowAttractions(true);onSelect(code,name);show('country',code,name,e.currentTarget);}}
        onBlur={e=>{if(!mapRoot.current?.contains(e.relatedTarget as Node))scheduleClose();}}
        onClick={e=>{if(drag.current?.moved)return;setShowAttractions(true);onSelect(code,name);show('country',code,name,e.currentTarget,e.clientX,e.clientY,true);}}
        onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(code,name);show('country',code,name,e.currentTarget,undefined,undefined,true);}}}><title>{name} · {visited.has(code)?'Visited':'Yet to explore'}</title></path>;})}
      <g className="map-waterways" aria-hidden="true">{lakes.map((d,index)=><path className="geographic-lake" key={`lake-${index}`} d={d}/>)}{rivers.map((d,index)=><path className="geographic-river" key={`river-${index}`} d={d} vectorEffect="non-scaling-stroke"/>)}</g>
      {zoom>1.3&&<g className="map-country-labels" aria-hidden="true">{geography?.labels.filter(label=>label.rank<=(zoom>3?5:3)&&Number.isFinite(label.lon)&&Number.isFinite(label.lat)).map(label=>{const [x,y]=project(label.lon,label.lat);return <text key={label.code3} x={x} y={y} textAnchor="middle" fontSize={11/zoom}>{countryNames.get(label.code3)}</text>;})}</g>}
      {showTrail&&<g className="recorded-memory-trail" aria-label="Chronological memory connections, not a GPS route">{trail.map((segment,index)=><g key={index}><path className="trail-casing" d={segment} vectorEffect="non-scaling-stroke"/><path className="trail-line" d={segment} vectorEffect="non-scaling-stroke"/></g>)}</g>}
      {markers.map(p=>{const [x,y]=project(p.lon,p.lat),isVisited=visitedPlaces.has(p.id),stop=stops.find(s=>s.place.id===p.id),number=stops.findIndex(s=>s.place.id===p.id)+1,active=activeStop?.place.id===p.id;
        const clip=`${gradientId}-${p.id}`;
        return <g key={p.id} transform={`translate(${x},${y}) scale(${1/zoom})`} className={`map-marker ${isVisited?'memory-marker photo-marker':'attraction-marker'} ${active?'active-step':''}`} tabIndex={0} role="button" aria-label={`${p.name}, ${isVisited?'view your memories':'explore attraction'}`}
        onMouseEnter={e=>show('place',p.id,p.name,e.currentTarget,e.clientX,e.clientY)} onMouseLeave={scheduleClose}
        onFocus={e=>{if(skipFocus.current){skipFocus.current=false;return;}show('place',p.id,p.name,e.currentTarget);}} onBlur={e=>{if(!mapRoot.current?.contains(e.relatedTarget as Node))scheduleClose();}}
        onClick={e=>{if(drag.current?.moved)return;show('place',p.id,p.name,e.currentTarget,e.clientX,e.clientY,true);}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show('place',p.id,p.name,e.currentTarget,undefined,undefined,true);}}}>
        {isVisited?<><defs><clipPath id={clip}><circle r="17"/></clipPath></defs><circle r="25" className="photo-pin-halo"/><circle r="20" className="photo-pin-frame"/><image href={memoryThumbnail(stop?.entry,p)} x="-17" y="-17" width="34" height="34" preserveAspectRatio="xMidYMid slice" clipPath={`url(#${clip})`} onError={e=>e.currentTarget.setAttribute('href',p.image)}/><circle cx="17" cy="-16" r="9" className="pin-count-circle"/><text x="17" y="-13" textAnchor="middle" className="pin-count">{number}</text><text x="0" y="35" textAnchor="middle" className="pin-place-label">{p.name}</text></>:<><circle r="13" className="marker-halo"/><circle r="5" className="marker-dot"/><text x="10" y="4" className="pin-place-label">{p.name}</text></>}
        <title>{p.name}</title></g>;
      })}
      <text x="175" y="175" className="ocean-label">PACIFIC OCEAN</text><text x="390" y="260" className="ocean-label">ATLANTIC</text><text x="700" y="335" className="ocean-label">INDIAN OCEAN</text>
    </svg>}
    <div className="map-navigation" aria-label="Map navigation"><button onClick={()=>zoomMap(1.45)} disabled={view.width<=125} aria-label="Zoom into map">+</button><button onClick={()=>zoomMap(1/1.45)} disabled={view.width>=1000} aria-label="Zoom out of map">−</button><span/><button onClick={()=>{setShowAttractions(false);setPreview(null);setView(fitPlaces(stops.map(s=>s.place)));}} disabled={!stops.length} aria-label="Fit all recorded memories on the map" title="Fit your memories">⌖</button><button onClick={()=>{setPreview(null);setView({...WORLD_VIEW});}} aria-label="Show the whole world" title="World view">◎</button></div>
    <div className="map-scale-label">{zoom.toFixed(1)}× <span>Drag to explore · Ctrl + scroll to zoom</span></div>
    <div className="memory-map-footer"><div className="map-bottom"><span className="map-hover" aria-live="polite">{hover||'Every stop has a story.'}</span><div className="legend"><span><i className="legend-visited"/>Visited</span><span><i className="legend-unvisited"/>Unexplored</span><span><i className="legend-trail"/>Memory connection</span></div></div>
    {stops.length>0&&<div className="map-memory-strip" aria-label="Your memories in chronological order">{stops.map(({entry,place},index)=><button key={entry.id} className={focusedEntryId===entry.id?'active':''} onClick={()=>focusStop(entry.id)} aria-label={`Focus memory ${index+1}, ${place.name}`} aria-pressed={focusedEntryId===entry.id}><span className="strip-step">{String(index+1).padStart(2,'0')}</span><img src={memoryThumbnail(entry,place)} alt=""/><span><strong>{place.name}</strong><small>{dateLabel(entry.visited_on)}</small></span></button>)}</div>}
    <p className="map-credit">Natural Earth · Borders, lakes, rivers & labels · Connections join journal dates, not a recorded GPS route. Generalized boundaries; close-up street detail is not available.</p></div>
    {popouts&&preview&&<section className="map-popout" ref={popout} tabIndex={-1} role="region" aria-label={`${preview.name} preview`} style={position} onMouseEnter={cancelClose} onMouseLeave={scheduleClose} onFocus={cancelClose} onBlur={e=>{if(!e.currentTarget.contains(e.relatedTarget as Node))scheduleClose();}}>
      <div className="popout-top"><span className="eyebrow">{previewEntries.length?'SOMEWHERE YOU’VE BEEN':'SOMEWHERE YOU COULD GO'}</span><button className="icon-button" aria-label="Close place preview" onClick={dismissPreview}><ExpandIcon close/></button></div>
      {previewPlace&&<img className="popout-cover" src={memoryThumbnail(previewEntries[0],previewPlace)} alt={`Memory preview for ${previewPlace.name}`}/>}
      <h3>{preview.name}</h3><p className="popout-subtitle">{previewPlace?.description||previewCountry?.subtitle||'A new corner of the world to discover.'}</p>
      {previewEntries.length>0&&<div className="popout-memories"><p className="eyebrow">YOUR MEMORIES</p>{previewEntries.map(e=><button key={e.id} className="popout-memory" onClick={()=>openMemory(e.id)}><span><strong>{e.title}</strong><small>{dateLabel(e.visited_on)}</small></span><span aria-hidden="true">↗</span></button>)}</div>}
      {previewPlaces.length>0?<div className="popout-attractions"><p className="eyebrow">{previewPlace?'WHEN TO GO':'A FEW PLACES TO START'}</p>{previewPlaces.map((p:Place)=><a className="popout-attraction" key={p.id} href={p.source} target="_blank" rel="noreferrer">{!previewPlace&&<img src={p.image} alt=""/>}<span><strong>{p.name}</strong><small>{p.season}</small></span><span aria-hidden="true">↗</span></a>)}<p className="popout-disclaimer">Illustrated previews · Seasonal notes are unverified. Links open official tourism sites.</p></div>:<p className="popout-empty">No curated attractions here yet. Explore Japan, India, Italy, France, or Thailand for workshop previews.</p>}
      <button className="popout-pin" aria-pressed={preview.pinned} onClick={()=>setPreview(p=>p?{...p,pinned:!p.pinned}:p)}>{preview.pinned?'◈ Kept open — click to unpin':'◈ Keep this preview open'}</button>
    </section>}
  </div>;

  return <>{!expanded&&stage}<dialog ref={dialog} className="fullscreen-map-dialog" aria-label="Fullscreen personal atlas" onCancel={e=>{e.preventDefault();closeExpanded();}}>{expanded&&stage}</dialog></>;
}
