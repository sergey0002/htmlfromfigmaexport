// Standalone checks using only local synthetic upstream and gate endpoints.
'use strict';
const assert=require('node:assert/strict');
const http=require('node:http');
const net=require('node:net');
const {createGate}=require('./network-http-gate.cjs');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function listen(server) {return new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',()=>resolve(server.address().port));});}
function send(port,payload) {return new Promise((resolve,reject)=>{
  const sock=net.createConnection({host:'127.0.0.1',port}); let data='';
  sock.setTimeout(5000,()=>sock.destroy(new Error('test timeout')));
  sock.on('connect',()=>sock.write(payload)); sock.on('data',chunk=>data+=chunk.toString('latin1'));
  sock.on('error',reject);sock.on('close',()=>resolve(data));
});}
function code(response) {const m=response.match(/^HTTP\/1\.1 (\d{3}) /);assert.ok(m,response);return Number(m[1]);}
(async()=>{
  const requests=[];
  const upstream=http.createServer((req,res)=>{
    requests.push({method:req.method,url:req.url,headers:req.headers});
    res.on('error',()=>{});
    if(req.url==='/external') {res.writeHead(302,{location:'http://evil.invalid/steal'});return res.end();}
    if(req.url==='/internal') {res.writeHead(302,{location:'/next?q=ok'});return res.end();}
    if(req.url==='/oversize') {res.writeHead(200,{'content-length':String(16*1024*1024+1)});return res.flushHeaders();}
    res.writeHead(200,{'content-type':'text/plain','set-cookie':'secret=1'});res.end('synthetic-ok');
  });
  let gate;
  try {
    const upstreamPort=await listen(upstream); const host=`127.0.0.1:${upstreamPort}`;
    gate=createGate(upstreamPort,host); const gatePort=await listen(gate);
    const request=(path,extra='')=>`GET ${path} HTTP/1.1\r\nHost: ${host}\r\n${extra}\r\n`;
    let response=await send(gatePort,request('/ok?x=1','Accept: text/plain\r\nCookie: private=1\r\nAuthorization: Bearer secret\r\nX-Forwarded-Host: attacker\r\n'));
    assert.equal(code(response),200); assert.match(response,/synthetic-ok/); assert.doesNotMatch(response,/set-cookie/i);
    assert.equal(requests.length,1); assert.equal(requests[0].url,'/ok?x=1');
    assert.equal(requests[0].headers.accept,'text/plain');
    for(const h of ['cookie','authorization','x-forwarded-host']) assert.equal(requests[0].headers[h],undefined);
    assert.equal(requests[0].headers['user-agent'],'synthetic-fixture-relay/1');
    response=await send(gatePort,`HEAD /ok HTTP/1.1\r\nHost: ${host}\r\n\r\n`); assert.equal(code(response),200);assert.doesNotMatch(response,/synthetic-ok/);
    const before=requests.length;
    const invalid=[
      [405,`POST / HTTP/1.1\r\nHost: ${host}\r\nContent-Length: 0\r\n\r\n`],
      [405,`DELETE / HTTP/1.1\r\nHost: ${host}\r\n\r\n`],
      [403,`GET / HTTP/1.1\r\nHost: ${host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n`],
      [405,`CONNECT evil.invalid:80 HTTP/1.1\r\nHost: ${host}\r\n\r\n`],
      [400,`GET / HTTP/1.1\r\nHost: evil.invalid\r\n\r\n`],
      [400,`GET / HTTP/1.1\r\nHost: ${host}\r\nHost: ${host}\r\n\r\n`],
      [400,`GET http://evil.invalid/path HTTP/1.1\r\nHost: ${host}\r\n\r\n`],
      [400,`GET //evil.invalid/path HTTP/1.1\r\nHost: ${host}\r\n\r\n`],
      [400,`GET / HTTP/1.1\r\nHost: ${host}\r\nContent-Length: 1\r\n\r\nx`],
      [400,`GET / HTTP/1.1\r\nHost: ${host}\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n`],
      [400,`GET / HTTP/1.1\r\nHost: ${host}\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n`],
      [417,`POST / HTTP/1.1\r\nHost: ${host}\r\nContent-Length: 1\r\nExpect: 100-continue\r\n\r\n`],
      [400,`GET / HTTP/1.0\r\nHost: ${host}\r\n\r\n`],
      [431,`GET / HTTP/1.1\r\nHost: ${host}\r\n`+Array.from({length:61},(_,i)=>`x-${i}: x\r\n`).join('')+'\r\n']
    ];
    for(const [expected,payload] of invalid) {response=await send(gatePort,payload);assert.equal(code(response),expected,response);}
    await sleep(50);assert.equal(requests.length,before,'rejected requests reached upstream');
    response=await send(gatePort,request('/external'));assert.equal(code(response),502);
    response=await send(gatePort,request('/internal'));assert.equal(code(response),302);assert.match(response,/location: \/next\?q=ok/i);
    response=await send(gatePort,request('/oversize'));assert.equal(code(response),502);
    const beforePipeline=requests.length;
    response=await send(gatePort,request('/first')+request('/second'));
    assert.equal(code(response),200);await sleep(50);
    assert.equal(requests.length,beforePipeline+1,'pipelined second request reached upstream');
    console.log('HTTP_GATE_TEST_OK');
  } finally {
    if(gate) {gate.closeAllConnections();await new Promise(resolve=>gate.close(resolve));}
    upstream.closeAllConnections();await new Promise(resolve=>upstream.close(resolve));
  }
})().catch(err=>{console.error(err);process.exitCode=1});
