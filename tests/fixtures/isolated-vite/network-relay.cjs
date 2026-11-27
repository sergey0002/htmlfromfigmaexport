// Trusted synthetic fixture relay. This is not a production security proxy.
const fs = require('node:fs');
require('/app/network-limits.cjs').assertLimits('relay');
const {createGate} = require('/app/network-http-gate.cjs');
const [socketPath,portString] = process.argv.slice(2);
const port = Number(portString);
if(socketPath !== '/bridge/target.sock' || ![4311,4312].includes(port)) throw Error('invalid fixture relay arguments');
if (!/CapEff:\s*0+\s/.test(fs.readFileSync('/proc/self/status','utf8'))) throw Error('relay capabilities not dropped');
if (!/NoNewPrivs:\s*1\s/.test(fs.readFileSync('/proc/self/status','utf8'))) throw Error('relay no_new_privs missing');
if (fs.existsSync('/app/secret-a.txt') || fs.existsSync('/app/secret-b.txt') || fs.existsSync('/home/user/htmlfromfigmaexport'))
  throw Error('fixture data visible inside relay root');
for(const fd of fs.readdirSync('/proc/self/fd')) {
  try { if(fs.readlinkSync('/proc/self/fd/'+fd).includes('/home/user/htmlfromfigmaexport')) throw Error('host project fd inherited'); }
  catch(err) { if(err.code!=='ENOENT') throw err; }
}
const server=createGate(port,`127.0.0.1:${port}`);
server.on('error',err=>{console.error(err);process.exitCode=1});
server.listen(socketPath,()=>{fs.chmodSync(socketPath,0o600); console.log('RELAY_READY '+port);});
