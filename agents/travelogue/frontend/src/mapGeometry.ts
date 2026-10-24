import type {Feature,Entry,Place} from './types';

export type MapView={x:number;y:number;width:number;height:number};
export const WORLD_VIEW:MapView={x:0,y:0,width:1000,height:470};

export function project(lon:number,lat:number) { return [(lon+180)*1000/360,(85-lat)*470/170]; }
export function countryPath(feature:Pick<Feature,'geometry'>) {
  const polygons=feature.geometry.type==='Polygon'?[feature.geometry.coordinates as number[][][]]:feature.geometry.coordinates as number[][][][];
  return polygons.map(p=>p.map(r=>r.map(([lon,lat],i)=>`${i?'L':'M'}${project(lon,lat).map(n=>n.toFixed(2)).join(',')}`).join(' ')+'Z').join(' ')).join(' ');
}

export function riverPath(points:number[][]) {
  return points.map(([lon,lat],index)=>`${index?'L':'M'}${project(lon,lat).map(n=>n.toFixed(2)).join(',')}`).join(' ');
}

export function popupPosition(width:number,height:number,x:number,y:number) {
  const popupWidth=Math.max(0,Math.min(316,width-24));
  const popupHeight=Math.max(170,Math.min(410,height-75));
  const desiredLeft=x+22+popupWidth>width-12?x-popupWidth-22:x+22;
  return {left:Math.max(12,Math.min(desiredLeft,width-popupWidth-12)),top:Math.max(48,Math.min(y-15,height-popupHeight-12)),width:popupWidth,maxHeight:popupHeight};
}

export function constrainView(view:MapView):MapView {
  const width=Math.max(125,Math.min(1000,view.width)),height=width*470/1000;
  return {width,height,x:Math.max(0,Math.min(1000-width,view.x)),y:Math.max(0,Math.min(470-height,view.y))};
}

export function zoomView(view:MapView,factor:number,anchor?:[number,number]):MapView {
  const width=Math.max(125,Math.min(1000,view.width/factor)),height=width*470/1000;
  const center=anchor||[view.x+view.width/2,view.y+view.height/2];
  return constrainView({width,height,x:center[0]-(center[0]-view.x)*width/view.width,y:center[1]-(center[1]-view.y)*height/view.height});
}

export function fitPlaces(places:Place[]):MapView {
  if(!places.length)return {...WORLD_VIEW};
  const points=places.map(p=>project(p.lon,p.lat)),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const width=Math.min(1000,Math.max(230,maxX-minX+150,(maxY-minY+90)*1000/470));
  return constrainView({x:(minX+maxX-width)/2,y:(minY+maxY-width*470/1000)/2,width,height:width*470/1000});
}

export function memoryStops(entries:Entry[],places:Place[]) {
  return [...entries].sort((a,b)=>a.visited_on.localeCompare(b.visited_on)||a.id.localeCompare(b.id))
    .flatMap(entry=>{const place=places.find(p=>p.id===entry.place_id);return place?[{entry,place}]:[];});
}

export function memoryTrail(stops:ReturnType<typeof memoryStops>) {
  const segments:string[]=[];
  for(let i=1;i<stops.length;i++){
    const a=stops[i-1].place,b=stops[i].place;
    if(a.id===b.id||Math.abs(a.lon-b.lon)>180)continue; // Do not draw long lines across the date line.
    const [x1,y1]=project(a.lon,a.lat),[x2,y2]=project(b.lon,b.lat);
    const bend=Math.min(55,Math.abs(x2-x1)*.14);
    segments.push(`M${x1},${y1}Q${(x1+x2)/2},${(y1+y2)/2-bend} ${x2},${y2}`);
  }
  return segments;
}

export function memoryThumbnail(entry:Entry|undefined,place:Place) {
  const photo=entry?.media?.find(m=>m.mime.startsWith('image/'));
  return photo?`/api/media/${photo.id}`:place.image;
}
