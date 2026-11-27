// Synthetic fixture assertions only. Per-process rlimits are not a sandbox.
'use strict';
const fs=require('node:fs');
const profiles={
  site:{'Max cpu time':'30','Max file size':'33554432','Max core file size':'0','Max open files':'256','Max address space':'68719476736'},
  relay:{'Max cpu time':'30','Max file size':'33554432','Max core file size':'0','Max open files':'256','Max address space':'68719476736'},
  browser:{'Max cpu time':'60','Max file size':'67108864','Max core file size':'0','Max open files':'512'}
};
function assertLimits(role) {
  const expected=profiles[role]; if(!expected) throw Error('unknown fixture rlimit role');
  const limits=fs.readFileSync('/proc/self/limits','utf8').split('\n');
  for(const [name,value] of Object.entries(expected)) {
    const row=limits.find(line=>line.startsWith(name+' '));
    if(!row) throw Error('missing fixture rlimit '+name);
    const fields=row.slice(name.length).trim().split(/\s+/);
    if(fields[0]!==value || fields[1]!==value) throw Error('incorrect fixture rlimit '+name+': '+row);
  }
  console.log('SYNTHETIC_RLIMITS_OK '+role);
}
module.exports={assertLimits};
