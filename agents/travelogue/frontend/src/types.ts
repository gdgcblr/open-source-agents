export type Place = { id:string; name:string; description:string; season:string; country:string; lon:number; lat:number; scene:string; color:string; source:string; image:string; evidence_status:string };
export type Country = { code:string; name:string; subtitle:string; color:string; source:string; places:Place[] };
export type Media = { id:string; filename:string; mime:string };
export type Entry = { id:string; country:string; place_id:string; title:string; visited_on:string; body:string; tags:string; published:boolean; media:Media[] };
export type Health = { provider:string; model:string; storage:string };
export type Activity = { place_id:string; title:string; note:string; estimate:string; source_ids:string[] };
export type Plan = { title:string; country:string; currency:string; travelers:number; days:{date:string; activities:Activity[]}[]; warnings:string[] };
export type StageState = 'pending'|'running'|'completed'|'failed';
export type Run = { id:string; status:string; stage:string; stages:string[]; provider:string; stage_states?:Record<string,StageState>; started_at?:string; updated_at?:string; finished_at?:string; deadline_seconds?:number; error?:string; result?:{itinerary:Plan; sources:{id:string; title:string; url:string}[]; provider:string; model:string; estimated_total:string; evaluation:Record<string,string>} };
export type Feature = {properties:{name:string;code:string;code3:string};geometry:{type:string; coordinates:number[][][]|number[][][][]}};
export async function api<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch('/api'+path, init);
  if (!response.ok) {
    const data = await response.json().catch(()=>({detail:'The server could not complete the request.'}));
    throw new Error(Array.isArray(data.detail) ? data.detail.map((e:{msg:string})=>e.msg).join(' ') : data.detail || 'Request failed.');
  }
  return response.status === 204 ? undefined as T : response.json();
}
export const json = (body:unknown,method='POST'):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const dateLabel=(s:string)=>new Date(s+'T12:00:00').toLocaleDateString(undefined,{day:'numeric',month:'long',year:'numeric'});
