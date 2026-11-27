// Synthetic fixture only; not an untrusted-runner or acceptance harness.
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const crypto = require('node:crypto');
require('/app/network-limits.cjs').assertLimits('browser');
const {chromium} = require('/app/playwright');
const hostPort=Number(process.argv[2]);
const artifactFd=Number(process.env.FIXTURE_ARTIFACT_FD);
const artifactFault=process.env.NETWORK_ARTIFACT_FAULT || 'none';
if (!Number.isInteger(hostPort)) throw Error('invalid host port');
if (!Number.isInteger(artifactFd) || artifactFd<3 || !fs.fstatSync(artifactFd).isFIFO()) throw Error('invalid artifact pipe');
if (!['none','corrupt','truncate','oversize','wronghash','kill-browser'].includes(artifactFault)) throw Error('invalid synthetic artifact fault');
function writeFrame(data,index) {
  if(!Buffer.isBuffer(data) || data.length===0 || data.length>2000000) throw Error('invalid synthetic capture length');
  const body=Buffer.from(data);
  if(index===0 && artifactFault==='corrupt') body[20]^=1;
  const header=Buffer.alloc(4);
  const claimed=index===0 && artifactFault==='oversize' ? 2000001 : data.length+(index===0 && artifactFault==='truncate' ? 100 : 0);
  header.writeUInt32BE(claimed);
  const frame=Buffer.concat([header,body]);
  for(let pos=0;pos<frame.length;) pos+=fs.writeSync(artifactFd,frame,pos,frame.length-pos);
}
for (const p of ['/app/secret-a.txt','/app/secret-b.txt','/home/user/htmlfromfigmaexport'])
  if (fs.existsSync(p)) throw Error('unexpected filesystem visibility: '+p);
if (!/CapEff:\s*0+\s/.test(fs.readFileSync('/proc/self/status','utf8'))) throw Error('capabilities not dropped');
if (!/NoNewPrivs:\s*1\s/.test(fs.readFileSync('/proc/self/status','utf8'))) throw Error('no_new_privs missing');
const visiblePids=fs.readdirSync('/proc').filter(name=>/^\d+$/.test(name));
if (visiblePids.join(',')!=='1') throw Error('unexpected process in private PID namespace: '+visiblePids);
try { process.kill(2,0); throw Error('another namespace process was visible'); }
catch (err) { if(err.code!=='ESRCH') throw err; }
const interfaces=require('node:os').networkInterfaces();
if(Object.keys(interfaces).some(name=>name!=='lo')) throw Error('unexpected network interface');
for(const fd of fs.readdirSync('/proc/self/fd')) {
  try { if(fs.readlinkSync('/proc/self/fd/'+fd).includes('/home/user/htmlfromfigmaexport')) throw Error('host project fd inherited'); }
  catch(err) { if(err.code!=='ENOENT') throw err; }
}
function hostProbe() { return new Promise((resolve,reject)=>{
  const req=http.get({host:'127.0.0.1',port:hostPort,path:'/',timeout:1000},res=>{res.resume();reject(Error('host loopback reachable'));});
  req.on('socket',s=>s.once('connect',()=>{req.destroy();reject(Error('host loopback TCP connection succeeded'));}));
  req.on('timeout',()=>req.destroy()); req.on('error',()=>resolve());
}); }
(async()=>{
  await hostProbe();
  // Before exposing browser-local bridges, neither site endpoint is directly reachable.
  for(const port of [4311,4312]) await new Promise((resolve,reject)=>{
    const sock=net.createConnection({host:'127.0.0.1',port});
    sock.setTimeout(1500,()=>{sock.destroy();resolve()});
    sock.once('connect',()=>{sock.destroy();reject(Error('direct site endpoint reachable'))});
    sock.once('error',()=>resolve());
  });
  console.log('BROWSER_DIRECT_ENDPOINTS_BLOCKED before local bridges');
  // The local bridge forwards bytes; the separate fixture relay applies limited HTTP checks.
  const proxies=[];
  for(const [name,port] of [['a',4311],['b',4312]]) {
    const proxy=net.createServer({pauseOnConnect:true},client=>{
      const upstream=net.createConnection({path:'/bridge/'+name+'/target.sock'});
      client.setTimeout(10000,()=>client.destroy()); upstream.setTimeout(10000,()=>upstream.destroy());
      client.on('error',()=>upstream.destroy()); upstream.on('error',()=>client.destroy());
      client.on('close',()=>upstream.destroy()); upstream.on('close',()=>client.destroy());
      upstream.on('connect',()=>{client.pipe(upstream).pipe(client);client.resume();});
    });
    proxy.maxConnections=32;
    await new Promise((resolve,reject)=>{proxy.once('error',reject);proxy.listen(port,'127.0.0.1',resolve)});
    proxies.push(proxy);
  }
  console.log('BROWSER_BRIDGES_READY separate browser network namespace');
  const sandbox=process.env.FIXTURE_BROWSER_SANDBOX==='1';
  const args=['--disable-dev-shm-usage','--disable-gpu','--disable-software-rasterizer'];
  if (!sandbox) args.push('--no-sandbox');
  const browser=await chromium.launch({executablePath:'/bin/chromium',chromiumSandbox:sandbox,args});
  if(sandbox) {
    // Verify the actual browser command line, not merely the requested flag.
    const commands=fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x)).map(pid=>{
      try { return fs.readFileSync('/proc/'+pid+'/cmdline','utf8'); } catch { return ''; }
    }).filter(cmd=>cmd.includes('/bin/chromium'));
    if(!commands.length || commands.some(cmd=>cmd.includes('--no-sandbox'))) throw Error('browser did not launch without --no-sandbox');
    console.log('BROWSER_SANDBOX_REQUESTED uid='+process.getuid()+' no --no-sandbox in observed chromium cmdlines');
  }
  try {
    const seen=[];
    for (const [port,expected] of [[4311,'Fixture A'],[4312,'Fixture B']]) {
      const ctx=await browser.newContext({serviceWorkers:'block',viewport:{width:390,height:844},deviceScaleFactor:1});
      try {
        await ctx.route('**/*',route=>{
          const u=new URL(route.request().url());
          if(u.protocol==='http:' && u.hostname==='127.0.0.1' && Number(u.port)===port && ['GET','HEAD'].includes(route.request().method())) return route.continue();
          return route.abort();
        });
        const page=await ctx.newPage(); await page.goto('http://127.0.0.1:'+port+'/',{waitUntil:'load'});
        const actual=await page.locator('h1').innerText(); if(actual!==expected) throw Error('unexpected page: '+actual);
        if (sandbox && seen.length===0) {
          const own=fs.readFileSync('/proc/self/status','utf8');
          const parentMatch=own.match(/^Seccomp_filters:\s*(\d+)/m);
          const renderers=fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x)).flatMap(pid=>{
            try {
              const cmd=fs.readFileSync('/proc/'+pid+'/cmdline','utf8');
              if (!cmd.includes('--type=renderer')) return [];
              const status=fs.readFileSync('/proc/'+pid+'/status','utf8');
              return [{seccomp:(status.match(/^Seccomp:\s*(\d+)/m)||[])[1],
                       filters:(status.match(/^Seccomp_filters:\s*(\d+)/m)||[])[1],
                       nspid:(status.match(/^NSpid:\s*(.*)/m)||[])[1]}];
            } catch { return []; }
          });
          if(!renderers.length || !parentMatch || !renderers.some(r=>r.seccomp==='2' && Number(r.filters)>Number(parentMatch[1])))
            throw Error('renderer extra seccomp filter not observed: '+JSON.stringify({parent:parentMatch,renderers}));
          console.log('RENDERER_FILTER_OK '+JSON.stringify({parent_filters:Number(parentMatch[1]),renderers}));
          // Observation only: /proc permissions can make some descriptors unreadable.
          const pipe=fs.readlinkSync('/proc/self/fd/'+artifactFd); let scanned=0,denied=0;
          for(const pid of fs.readdirSync('/proc').filter(x=>/^\d+$/.test(x))) {
            try {
              if(!fs.readFileSync('/proc/'+pid+'/cmdline','utf8').includes('/bin/chromium')) continue;
              for(const fd of fs.readdirSync('/proc/'+pid+'/fd')) {
                try { if(fs.readlinkSync('/proc/'+pid+'/fd/'+fd)===pipe) throw Error('artifact pipe visible in chromium process'); }
                catch(e) { if(e.code==='ENOENT') continue; if(['EACCES','EPERM'].includes(e.code)) {denied++;continue;} throw e; }
              }
              scanned++;
            } catch(e) { if(e.code==='ENOENT') continue; if(['EACCES','EPERM'].includes(e.code)) {denied++;continue;} throw e; }
          }
          console.log('ARTIFACT_FD_OBSERVATION '+JSON.stringify({scanned,denied}));
        }
        seen.push(actual);
        const screenshot=await page.screenshot();
        if(!screenshot.length) throw Error('empty synthetic screenshot');
        writeFrame(screenshot,seen.length-1);
        // Parent kills the process group after reading the first frame; stay alive
        // here so the injected failure cannot race the second capture.
        if(artifactFault==='kill-browser' && seen.length===1) await new Promise(()=>{});
        const digest=artifactFault==='wronghash' && seen.length===1 ? '0'.repeat(64) : crypto.createHash('sha256').update(screenshot).digest('hex');
        console.log('SCREEN_SHA256 '+digest);
      } finally { await ctx.close(); }
    }
    if(seen.join(',')!=='Fixture A,Fixture B') throw Error('independent views not reached');
    fs.closeSync(artifactFd);
  } finally { await browser.close(); for (const proxy of proxies) await new Promise(resolve=>proxy.close(resolve)); }
  console.log('BROWSER_OK separate root, PID and network namespaces, no caps, no_new_privs, host loopback blocked');
})().catch(err=>{console.error(err);process.exitCode=1});
