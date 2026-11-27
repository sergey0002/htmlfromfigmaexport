const {spawn} = require('node:child_process');
const http = require('node:http'); const fs = require('node:fs');
const children = [];
function launch(name, port) {
  const child=spawn(process.execPath,['/app/node_modules/vite/bin/vite.js','/app/'+name,'--host','127.0.0.1','--port',String(port),'--strictPort'],{env:{PATH:'/bin',HOME:'/tmp',NODE_ENV:'development'}});
  children.push(child);
  return new Promise((resolve,reject)=>{
    let output=''; const timer=setTimeout(()=>reject(new Error('startup timeout: '+output)),10000);
    child.stdout.on('data',d=>{ output+=d; if(output.includes('Local:')) {clearTimeout(timer);resolve(child);} });
    child.stderr.on('data',d=>output+=d);
    child.on('exit',c=>{clearTimeout(timer);reject(new Error('early exit '+c+': '+output))});
  });
}
function request(port) { return new Promise((resolve,reject)=>{ http.get('http://127.0.0.1:'+port+'/',r=>{let s='';r.on('data',d=>s+=d);r.on('end',()=>resolve(s));}).on('error',reject); }); }
(async()=>{
  if(fs.existsSync('/home/user/htmlfromfigmaexport')) throw Error('Unexpected host filesystem exposure');
  if(!/CapEff:\s*0+\s/.test(fs.readFileSync('/proc/self/status','utf8'))) throw Error('Capabilities not dropped');
  let hostReachable=false; try { await request(Number(process.env.HOST_TEST_PORT)); hostReachable=true; } catch {}
  if(hostReachable) throw Error('Host loopback unexpectedly reachable');
  await Promise.all([launch('a',4311),launch('b',4312)]);
  const [a,b] = await Promise.all([request(4311),request(4312)]);
  if(!a.includes('Reference A') || !b.includes('Reference B') || a===b) throw Error('wrong server response');
  const {chromium}=require('/app/playwright');
  const browser=await chromium.launch({executablePath:'/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer']});
  try { const page=await browser.newPage(); await page.goto('http://127.0.0.1:4311/'); const first=await page.locator('h1').innerText(); await page.goto('http://127.0.0.1:4312/'); const second=await page.locator('h1').innerText(); if(first!=='Fixture A'||second!=='Fixture B') throw Error('browser reached wrong site: '+JSON.stringify({first,second})); await page.screenshot({path:'/tmp/synthetic.png'}); } finally { await browser.close(); }
  let conflict=false;
  try { await launch('a',4311); } catch(e) { conflict=/address already in use|EADDRINUSE|Port 4311 is already in use/i.test(e.message); }
  if(!conflict) throw Error('port conflict was not rejected');
  console.log('OK synthetic React 18.3.1 + Vite 5.4.21 + Chromium: two endpoints, strict port conflict, host loopback inaccessible, no host project, zero capabilities');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>{for(const p of children) if(!p.killed) p.kill('SIGTERM');});
