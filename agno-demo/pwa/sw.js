const CACHE='kc-agency-v21';
const ASSETS=['/','/index.html','/styles.css?v=21','/app.js?v=21','/agency-v2.webmanifest','/agency-touch-180-v3.png','/agency-touch-192-v3.png','/agency-touch-512-v3.png','/agency-v2.webmanifest'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)));self.skipWaiting();});
self.addEventListener('activate',e=>e.waitUntil((async()=>{for(const k of await caches.keys())if(k!==CACHE&&(k.startsWith('moya-komanda-')||k.startsWith('kc-shell-')||k.startsWith('kc-agency-')))await caches.delete(k);await self.clients.claim();})()));
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==self.location.origin||u.pathname.startsWith('/api/'))return;
 if(!ASSETS.some(a=>new URL(a,self.location.origin).pathname===u.pathname))return;
 e.respondWith((async()=>{
  try{const r=await fetch(e.request);if(r.ok&&!r.redirected){const c=await caches.open(CACHE);await c.put(e.request,r.clone());}return r;}
  catch{const cached=await caches.match(e.request);return cached||new Response('Нет связи. Откройте приложение, когда сервер доступен.',{status:503,headers:{'Content-Type':'text/plain; charset=utf-8'}});}
 })());
});