/* FieldKey mission package: tile planning and size estimate.
   A line-for-line port of worker/fieldkey_export/tiles.py so the phone shows the same size the
   worker will enforce. Both are tested against worker/tests/fixtures/export_estimate.json. */
(function(root, factory){
  if(typeof module==="object"&&module.exports) module.exports=factory(); else root.FKExport=factory();
})(typeof self!=="undefined"?self:this, function(){
  "use strict";
  const WORLD=20037508.342789244, MAX_LAT=85.0511287798066;
  const FULL_AREA_TILES=64, PLAN_TILE_LIMIT=250000;
  const BASE_BYTES=480*1024, BYTES_PER_FEATURE=1000;

  const clamp=(v,lo,hi)=>v<lo?lo:v>hi?hi:v;
  const rad=d=>d*Math.PI/180;

  function lonlatToTile(lon,lat,z){
    const n=2**z; lat=clamp(lat,-MAX_LAT,MAX_LAT);
    const x=Math.trunc((lon+180)/360*n);
    const y=Math.trunc((1-Math.asinh(Math.tan(rad(lat)))/Math.PI)/2*n);
    return [clamp(x,0,n-1)+0, clamp(y,0,n-1)+0];   // +0 turns -0 into 0, like Python int()
  }
  function tileRange(b,z){ const a=lonlatToTile(b[0],b[3],z), c=lonlatToTile(b[2],b[1],z); return [a[0],a[1],c[0],c[1]]; }
  function bufferBbox(b,m){
    const mid=rad(clamp((b[1]+b[3])/2,-89,89)), dlat=m/111320, dlon=m/(111320*Math.max(Math.cos(mid),0.01));
    return [Math.max(b[0]-dlon,-180), Math.max(b[1]-dlat,-MAX_LAT), Math.min(b[2]+dlon,180), Math.min(b[3]+dlat,MAX_LAT)];
  }
  function unionBbox(bs){
    if(!bs.length) return null;
    return [Math.min(...bs.map(b=>b[0])), Math.min(...bs.map(b=>b[1])), Math.max(...bs.map(b=>b[2])), Math.max(...bs.map(b=>b[3]))];
  }
  /* Returns {perZoom:{z:count}, total, truncated}. Same rule as the worker: whole area while it's
     small, otherwise only tiles near each feature. */
  function planTiles(boxes,minZoom,maxZoom,limit){
    limit=limit||PLAN_TILE_LIMIT; boxes=boxes.filter(Boolean);
    const area=unionBbox(boxes), perZoom={}; let total=0;
    if(!area) return {perZoom,total:0,truncated:false};
    for(let z=minZoom; z<=maxZoom; z++){
      const [x0,y0,x1,y1]=tileRange(area,z); let count;
      if((x1-x0+1)*(y1-y0+1)<=FULL_AREA_TILES) count=(x1-x0+1)*(y1-y0+1);
      else{
        const s=new Set();
        for(const b of boxes){
          const [a0,b0,a1,b1]=tileRange(b,z);
          for(let x=a0;x<=a1;x++) for(let y=b0;y<=b1;y++) s.add(x*16777216+y);
          if(total+s.size>limit) break;
        }
        count=s.size;
      }
      perZoom[z]=count; total+=count;
      if(total>limit) return {perZoom,total,truncated:true};
    }
    return {perZoom,total,truncated:false};
  }
  /* Same rule as planTiles, but returns the tiles themselves: {byZoom:{z:[[x,y]]}, total, truncated}.
     Used by "Save mission offline", which caches these tiles on the phone. fullArea (default 64, the
     package rule) is how many tiles a zoom level may have and still be taken whole; the phone passes
     a larger number so the map between sites isn't blank. */
  function planTileList(boxes,minZoom,maxZoom,limit,fullArea){
    limit=limit||PLAN_TILE_LIMIT; fullArea=fullArea||FULL_AREA_TILES; boxes=boxes.filter(Boolean);
    const area=unionBbox(boxes), byZoom={}; let total=0;
    if(!area) return {byZoom,total:0,truncated:false};
    for(let z=minZoom; z<=maxZoom; z++){
      const [x0,y0,x1,y1]=tileRange(area,z), s=new Map();
      if((x1-x0+1)*(y1-y0+1)<=fullArea){
        for(let x=x0;x<=x1;x++) for(let y=y0;y<=y1;y++) s.set(x*16777216+y,[x,y]);
      }else{
        for(const b of boxes){
          const [a0,b0,a1,b1]=tileRange(b,z);
          for(let x=a0;x<=a1;x++) for(let y=b0;y<=b1;y++) s.set(x*16777216+y,[x,y]);
          if(total+s.size>limit) break;
        }
      }
      byZoom[z]=[...s.values()]; total+=s.size;
      if(total>limit) return {byZoom,total,truncated:true};
    }
    return {byZoom,total,truncated:false};
  }
  function fillTemplate(tpl,z,x,y){ return tpl.replace(/\{z\}/g,z).replace(/\{x\}/g,x).replace(/\{y\}/g,y); }
  /* layers: [{tpl, z0, z1}] → unique tile URLs for the planned tiles inside each layer's zoom range. */
  function layerUrls(layers,byZoom){
    const out=new Set();
    for(const L of layers) for(let z=L.z0; z<=L.z1; z++) for(const [x,y] of (byZoom[z]||[])) out.add(fillTemplate(L.tpl,z,x,y));
    return [...out];
  }
  function estimateBytes(featureCount,tileCounts){
    return BASE_BYTES+featureCount*BYTES_PER_FEATURE+tileCounts.reduce((s,[n,avg])=>s+Math.trunc(n*avg),0);
  }
  /* points: [[lon,lat]]; sources: [{id,min_zoom,max_zoom,avg_tile_bytes}] */
  function estimatePackage(points,featureCount,sources,opts){
    const boxes=points.map(([lo,la])=>bufferBbox([lo,la,lo,la],opts.bufferM));
    const per=sources.map(s=>{
      const lo=Math.max(opts.minZoom,s.min_zoom), hi=Math.min(opts.maxZoom,s.max_zoom);
      const p=lo>hi?{total:0,truncated:false}:planTiles(boxes,lo,hi);
      return {id:s.id, tiles:p.total, truncated:p.truncated, bytes:Math.trunc(p.total*s.avg_tile_bytes)};
    });
    return {bytes:estimateBytes(featureCount,per.map(p=>[p.tiles,sources.find(s=>s.id===p.id).avg_tile_bytes])),
            tiles:per.reduce((s,p)=>s+p.tiles,0), truncated:per.some(p=>p.truncated), perSource:per};
  }
  return {lonlatToTile,tileRange,bufferBbox,unionBbox,planTiles,planTileList,fillTemplate,layerUrls,estimateBytes,estimatePackage,BASE_BYTES,BYTES_PER_FEATURE};
});
