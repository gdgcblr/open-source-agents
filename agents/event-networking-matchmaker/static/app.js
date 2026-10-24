const $ = id => document.getElementById(id);
// Fragment credentials are not sent in HTTP requests; clear before API activity.
const invitation = new URLSearchParams(location.hash.slice(1));
if(invitation.has('token')) history.replaceState(null,'',location.pathname+location.search);
let events = [], sample = [], token = '', eventName = '', me = null;
let requestVersion = 0;
const text = (tag, value, cls) => { const e = document.createElement(tag); e.textContent = value; if(cls)e.className=cls; return e; };
function notice(message, error=false){ $('notice').textContent=message; $('notice').classList.toggle('error',error); }
async function api(path, options={}){
  const headers = {...(token ? {Authorization:`Bearer ${token}`} : {}), ...options.headers};
  if(options.body && !(options.body instanceof FormData)) {headers['Content-Type']='application/json'; options.body=JSON.stringify(options.body);}
  const response=await fetch(path,{...options,headers});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the submitted fields and try again.');
  return data;
}
const url = path => `${path}?event=${encodeURIComponent(eventName)}`;
function option(select, value, label){const o=text('option',label);o.value=value;select.append(o);}
async function loadEvents(){
  events=await api('/api/events');$('event').replaceChildren();
  option($('event'),'','Choose your event');
  events.forEach(e=>option($('event'),e.name,e.name));
  if(!events.length)notice('No events yet. Open the organizer workspace to import responses, or restart with --demo to explore the sample.');
}
function signout(){requestVersion++;token='';eventName='';me=null;$('token').value='';$('attendee').classList.add('hidden');$('login').classList.remove('hidden');$('results').replaceChildren();$('trace-text').textContent='';$('sample-person').value='';}
async function login(name, privateToken){
  eventName=name;token=privateToken;
  try{me=await api(url('/api/me'));}catch(e){signout();throw e;}
  $('welcome').textContent=`Hi ${me.name}. Let’s make a useful introduction.`;
  $('profile-summary').textContent=`You offer ${me.offers} · You’re looking for ${me.needs || 'new connections'}`;
  $('badge').textContent=me.id;$('spot').replaceChildren();
  (events.find(e=>e.name===name)?.spots||[]).forEach(s=>option($('spot'),s,s));
  $('window').replaceChildren();option($('window'),'','Any networking window');
  me.window.split(/[,;\n]/).map(s=>s.trim()).filter(Boolean).forEach(s=>option($('window'),s.toLowerCase(),s));
  $('query').value='';$('active-only').checked=false;
  $('offered-only').checked=false;
  $('login').classList.add('hidden');$('attendee').classList.remove('hidden');
  notice('Signed in. Your private token stays in this page’s memory and is cleared when you sign out.');
  showPresence();await findMatches();
}
function showPresence(){
  const active=me && me.until_ts*1000>Date.now();
  $('presence').textContent=active?`Last checked in at ${me.spot}. Expires ${new Date(me.until_ts*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}.`:'You are not currently checked in.';
}
async function findMatches(){
  const version=++requestVersion, sessionToken=token;
  $('match-submit').disabled=true;$('match-submit').textContent='Finding useful introductions…';
  try{
    const data=await api(url('/api/matches'),{method:'POST',body:{query:$('query').value,window:$('window').value,active_only:$('active-only').checked,use_ai:$('use-ai').checked,offered_only:$('offered-only').checked}});
    if(version!==requestVersion||sessionToken!==token)return;
    $('results').replaceChildren();$('result-meta').textContent=`${data.matches.length} ${data.matches.length===1?'match':'matches'} · ${data.latency_ms} ms`;
    notice(data.warning||`${data.mode}. ${data.privacy}`);
    if(!data.matches.length)$('results').append(text('div',data.message,'empty'));
    for(const p of data.matches){
      const card=text('article','','match-card'), top=text('div','','match-top'), who=text('div','');
      who.append(text('h3',p.name),text('span',`Badge ${p.id}`,'code'));top.append(who,text('span',p.label,'pill'));card.append(top,text('p',p.project||'Open to a conversation','project'));
      card.append(text('p',p.reason,'reason'),text('p',p.caveat,'hint'));
      const benefits=text('div','','benefits');
      for(const [label,values,empty] of [['Direct skill overlap',p.helps_you,'See the related evidence above'],['You can offer',p.you_help,'No reciprocal skill overlap listed']]){
        const box=text('div','');box.append(text('strong',label),text('p',values.join(', ')||empty));benefits.append(box);
      }card.append(benefits);
      if(p.shared.length)card.append(text('p',`Shared interests: ${p.shared.join(', ')}`,'hint'));
      const evidence=text('details','','evidence');evidence.append(text('summary','See the profile evidence'));
      for(const e of p.evidence)evidence.append(text('p',`${e.field}: ${e.text}`,'hint'));
      card.append(evidence);
      card.append(text('div',p.starter,'starter'));
      const location=text('p','','location');location.dataset.expiry=p.until_ts||0;location.dataset.spot=p.spot||'';
      location.textContent=p.spot?`Last checked in at ${p.spot} · available until ${new Date(p.until_ts*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}`:`Not checked in · preferred window: ${p.window}`;
      card.append(location);const met=text('button','We’ve met','quiet');
      met.addEventListener('click',async()=>{try{await api(url(`/api/met/${encodeURIComponent(p.id)}`),{method:'POST'});await findMatches();}catch(e){notice(e.message,true);}});card.append(met);$('results').append(card);
    }
    $('trace').classList.remove('hidden');$('trace-text').textContent=JSON.stringify({engine:data.mode,interpreted_topics:data.skills,steps:data.trace},null,2);
  }finally{if(version===requestVersion){$('match-submit').disabled=false;$('match-submit').textContent='Find useful introductions ↗';}}
}
function handle(id, fn){$(id).addEventListener('submit',async e=>{e.preventDefault();const b=e.target.querySelector('button[type="submit"]');if(b)b.disabled=true;try{await fn();}catch(err){notice(err.message,true);}finally{if(b)b.disabled=false;}});}
handle('login-form',()=>login($('event').value,$('token').value.trim()));
handle('match-form',findMatches);
handle('checkin-form',async()=>{await api(url('/api/checkin'),{method:'POST',body:{spot:$('spot').value,minutes:Number($('minutes').value)}});me=await api(url('/api/me'));showPresence();notice('Check-in saved. Other attendees can now find your meeting spot.');});
$('checkout').onclick=async()=>{try{await api(url('/api/checkin'),{method:'DELETE'});me=await api(url('/api/me'));showPresence();}catch(e){notice(e.message,true);}};
$('logout').onclick=()=>{signout();notice('Signed out.');};
$('reset-met').onclick=async()=>{try{await api(url('/api/met'),{method:'DELETE'});await findMatches();}catch(e){notice(e.message,true);}};
$('withdraw').onclick=async()=>{if(!confirm('Remove your profile and check-in from this event? Your attendee ID will remain excluded from future imports for this event.'))return;try{await api(url('/api/me'),{method:'DELETE'});signout();notice('Profile removed. Your old access token is no longer valid, and reimports will not restore your profile.');}catch(e){notice(e.message,true);}};
$('organizer-toggle').onclick=()=>{$('organizer').classList.toggle('hidden');$('admin-tools').classList.toggle('hidden');if(!$('organizer').classList.contains('hidden'))$('organizer').scrollIntoView({behavior:'smooth'});};
handle('import-form',async()=>{
  const importedEvent=$('import-event').value.trim();
  const form=new FormData();form.append('event',importedEvent);form.append('spots',$('import-spots').value);form.append('file',$('import-file').files[0]);
  const result=await api('/api/import',{method:'POST',body:form,headers:{Authorization:`Bearer ${$('admin-key').value.trim()}`}});
  $('admin-key').value='';$('import-result').replaceChildren(text('p',`${result.imported} profiles imported; ${result.skipped} non-consenting or previously withdrawn rows skipped.`),text('p',result.note,'hint'));
  if(result.credentials.length){const button=text('button','Download new private access tokens');button.type='button';button.onclick=()=>{
    const credentials=result.credentials.map(c=>({...c,invite_url:`${location.origin}/#${new URLSearchParams({event:importedEvent,token:c.token})}`}));
    const blob=new Blob([JSON.stringify({event:importedEvent,credentials},null,2)],{type:'application/json'});
    const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='private-attendee-tokens.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);
  };$('import-result').append(button,text('p','Keep this file private. Give each attendee only their own token. Tokens cannot be recovered after leaving this page.','hint'));}
  await loadEvents();notice('Import complete. Share private access tokens individually with attendees.');
});
$('sample-person').onchange=async()=>{const p=sample.find(p=>p.id===$('sample-person').value);if(p)try{await login('BuildBuddy Sample Event',p.token);}catch(e){notice(e.message,true);}};
document.querySelectorAll('[data-goal]').forEach(button=>button.onclick=async()=>{$('query').value=button.dataset.goal;try{await findMatches();}catch(e){notice(e.message,true);}});
handle('manage-form',async()=>{
  const id=$('manage-id').value.trim(),event=$('manage-event').value.trim();
  if(!id)throw new Error('Enter the attendee ID whose token needs replacing.');
  const result=await api(`/api/admin/rotate/${encodeURIComponent(id)}?event=${encodeURIComponent(event)}`,{method:'POST',headers:{Authorization:`Bearer ${$('manage-key').value.trim()}`}});
  $('manage-key').value='';$('manage-result').replaceChildren(text('p','Old token revoked. Give this replacement only to the verified attendee:'),text('pre',`${result.id}: ${result.token}`));
});
$('delete-event').onclick=async()=>{
  const name=$('manage-event').value.trim(),key=$('manage-key').value.trim();
  if(!name||!key){notice('Enter the organizer key and event name first.',true);return;}
  if(!confirm(`Permanently delete all BuildBuddy data for ${name}? Your source spreadsheet and downloaded token files are not deleted.`))return;
  try{const result=await api(`/api/admin/event?event=${encodeURIComponent(name)}`,{method:'DELETE',headers:{Authorization:`Bearer ${key}`}});$('manage-key').value='';$('manage-result').replaceChildren(text('p',result.message));if(eventName===name)signout();await loadEvents();}catch(e){notice(e.message,true);}
};
setInterval(()=>{if(me)showPresence();document.querySelectorAll('.location[data-expiry]').forEach(el=>{if(Number(el.dataset.expiry)>0&&Number(el.dataset.expiry)*1000<=Date.now())el.textContent='Check-in expired. Refresh matches for current availability.';});},15000);
(async()=>{try{await loadEvents();const config=await api('/api/config');$('engine').textContent=`${config.engine} · attendee profiles stay here`;$('use-ai').disabled=!config.ai_available;if(!config.ai_available)$('ai-note').textContent='Cloud planner is not configured. Local NLP searches skills, interests, and projects without any API key.';if(config.warning)notice(config.warning);if(config.demo){sample=await api('/api/demo');sample.forEach(p=>option($('sample-person'),p.id,`${p.name} · ${p.id}`));$('sample-banner').classList.remove('hidden');}}catch(e){notice(e.message,true);}})();
// Wait for initial configuration/events before using the private invitation.
window.addEventListener('load',async()=>{
  if(!invitation.has('token'))return;
  try{
    await loadEvents();
    await login(invitation.get('event')||'',invitation.get('token')||'');
    notice('Your pre-event matches are ready. This signs you in, but does not announce a venue arrival. Check in at a meeting spot only when you arrive.');
  }catch(e){notice(e.message,true);}
  finally{invitation.delete('token');invitation.delete('event');}
});
