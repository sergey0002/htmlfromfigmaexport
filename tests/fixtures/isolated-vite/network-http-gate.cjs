// Fixture-only HTTP relay. Not a production proxy, sandbox or trust guarantee.
'use strict';
const http = require('node:http');

const REQUEST_HEADERS = ['accept', 'accept-language', 'range', 'if-none-match', 'if-modified-since'];
const RESPONSE_HEADERS = ['content-type', 'content-length', 'content-encoding', 'cache-control',
  'etag', 'last-modified', 'vary', 'content-range', 'accept-ranges', 'content-security-policy',
  'x-content-type-options', 'x-frame-options'];
const MAX_RESPONSE=16*1024*1024;

function createGate(port, expectedHost) {
  if (!Number.isInteger(port) || port<1 || port>65535 || expectedHost!==`127.0.0.1:${port}`) throw Error('invalid fixture gate');
  const seen=new WeakSet();
  function refuse(req,res,status) {
    res.writeHead(status, {'Connection':'close','Content-Length':'0'}); res.end();
    req.resume();
  }
  const server=http.createServer({maxHeaderSize:8192}, (req,res)=>{
    if (seen.has(req.socket)) return refuse(req,res,400); // no HTTP keepalive or pipelining
    seen.add(req.socket);
    if(req.rawHeaders.length>120) return refuse(req,res,431);
    const names=new Set();
    for(let i=0;i<req.rawHeaders.length;i+=2) {
      const name=req.rawHeaders[i].toLowerCase();
      if(names.has(name)) return refuse(req,res,400);
      names.add(name);
    }
    if(req.httpVersion!=='1.1' || req.headers.host!==expectedHost) return refuse(req,res,400);
    if(req.method!=='GET' && req.method!=='HEAD') return refuse(req,res,405);
    if(!req.url || req.url.length>2048 || !req.url.startsWith('/') || req.url.startsWith('//') || /[^\x21-\x7e]|#|\\/.test(req.url)) return refuse(req,res,400);
    if(req.headers['transfer-encoding']!==undefined || (req.headers['content-length']!==undefined && req.headers['content-length']!=='0')) return refuse(req,res,400);
    if(req.headers.upgrade!==undefined || /(?:^|,)\s*upgrade\s*(?:,|$)/i.test(req.headers.connection||'')) return refuse(req,res,403);
    const headers={host:expectedHost, connection:'close', 'user-agent':'synthetic-fixture-relay/1'};
    for(const name of REQUEST_HEADERS) if(typeof req.headers[name]==='string') headers[name]=req.headers[name];
    const upstream=http.request({host:'127.0.0.1',port,method:req.method,path:req.url,headers,agent:false}, response=>{
      const output={'connection':'close'};
      for(const name of RESPONSE_HEADERS) if(typeof response.headers[name]==='string') output[name]=response.headers[name];
      const length=response.headers['content-length'];
      if(length!==undefined && (!/^\d+$/.test(length) || Number(length)>MAX_RESPONSE)) {
        response.destroy(); if(!res.headersSent) refuse(req,res,502); else res.destroy(); return;
      }
      if(typeof response.headers.location==='string') {
        let target;
        try { target=new URL(response.headers.location,`http://${expectedHost}${req.url}`); }
        catch { response.destroy(); return refuse(req,res,502); }
        if(target.origin!==`http://${expectedHost}` || target.username || target.password) {
          response.destroy(); return refuse(req,res,502);
        }
        output.location=target.pathname+target.search+target.hash;
      }
      res.writeHead(response.statusCode || 502,output);
      let count=0;
      response.on('data',chunk=>{
        count+=chunk.length;
        if(count>MAX_RESPONSE) {response.destroy();res.destroy();}
      });
      response.on('error',()=>res.destroy());
      response.pipe(res);
    });
    const timeout=setTimeout(()=>upstream.destroy(new Error('fixture upstream timeout')),10000);
    upstream.on('error',()=>{if(!res.headersSent) refuse(req,res,502); else res.destroy();});
    res.on('close',()=>{clearTimeout(timeout);upstream.destroy();});
    upstream.end();
  });
  server.maxConnections=32; server.maxHeadersCount=0;
  server.headersTimeout=5000; server.requestTimeout=7000;
  server.setTimeout(10000,socket=>socket.destroy());
  server.on('clientError',(_err,socket)=>{if(socket.writable) socket.end('HTTP/1.1 400 Bad Request\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');});
  server.on('upgrade',(_req,socket)=>socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'));
  server.on('connect',(_req,socket)=>socket.end('HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'));
  const expectation=(_req,res)=>{res.writeHead(417,{'Connection':'close','Content-Length':'0'});res.end();};
  server.on('checkContinue',expectation); server.on('checkExpectation',expectation);
  return server;
}
module.exports={createGate};
