// Synthetic trusted fixture, never a generic entry point for project code.
const fs = require('node:fs');
const http = require('node:http');
const {spawn} = require('node:child_process');
const [name, port, hostPort] = process.argv.slice(2);
if (!['a','b'].includes(name) || !/^\d+$/.test(port) || !/^\d+$/.test(hostPort)) throw Error('invalid synthetic parameters');
const other = name === 'a' ? '/app/secret-b.txt' : '/app/secret-a.txt';
if (!fs.existsSync('/app/secret-'+name+'.txt') || fs.existsSync(other)) throw Error('chroot does not separate fixture data');
if (fs.existsSync('/home/user/htmlfromfigmaexport')) throw Error('host project visible');
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
// PID 1 is this fixture or its private namespace supervisor, never a peer.
const cmdline=fs.readFileSync('/proc/1/cmdline','utf8');
if (cmdline.includes('separated-browser') || cmdline.includes('secret-'+(name==='a'?'b':'a'))) throw Error('peer PID visible');
function hostProbe() { return new Promise((resolve,reject) => {
  const req=http.get({host:'127.0.0.1',port:Number(hostPort),path:'/',timeout:1000}, res=>{res.resume();reject(Error('host loopback reachable'));});
  req.on('socket',s=>s.once('connect',()=>{req.destroy();reject(Error('host loopback TCP connection succeeded'));}));
  req.on('timeout',()=>req.destroy()); req.on('error',()=>resolve());
}); }
(async()=>{
  await hostProbe();
  console.log('PROBE_OK '+name);
  const child=spawn(process.execPath,['/app/node_modules/vite/bin/vite.js','/app/site','--host','127.0.0.1','--port',port,'--strictPort'],
    {env:{PATH:'/bin',HOME:'/tmp',NODE_ENV:'development'},stdio:['ignore','pipe','pipe']});
  child.stdout.pipe(process.stdout); child.stderr.pipe(process.stderr);
  child.on('exit',(code,signal)=>{process.exitCode=code === null ? 1 : code;});
  for(const sig of ['SIGTERM','SIGINT']) process.on(sig,()=>{child.kill(sig);});
})().catch(err=>{console.error(err);process.exitCode=1;});
