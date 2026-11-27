// Synthetic fixture only; not an untrusted-runner or acceptance harness.
const fs = require('node:fs');
const http = require('node:http');
const crypto = require('node:crypto');
const {chromium} = require('/app/playwright');
const hostPort=Number(process.argv[2]);
if (!Number.isInteger(hostPort)) throw Error('invalid host port');
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
      const ctx=await browser.newContext({serviceWorkers:'block'});
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
        }
        seen.push(actual);
        const screenshot=await page.screenshot();
        if(!screenshot.length) throw Error('empty synthetic screenshot');
        console.log('SCREEN_SHA256 '+crypto.createHash('sha256').update(screenshot).digest('hex'));
      } finally { await ctx.close(); }
    }
    if(seen.join(',')!=='Fixture A,Fixture B') throw Error('independent views not reached');
  } finally { await browser.close(); }
  console.log('BROWSER_OK separate root, PID namespace, no caps, no_new_privs, host loopback blocked');
})().catch(err=>{console.error(err);process.exitCode=1});
