const {test}=require('node:test'),assert=require('node:assert/strict');
const picker=require('../features/folder-picker');
test('folder selection preserves unicode and cancellation',async()=>{const path='D:\\工程\\项目';const execFile=(exe,args,options,cb)=>{assert.equal(exe,'powershell.exe');assert.ok(args.includes('-STA'));cb(null,Buffer.from(path).toString('base64')+'\n');};assert.equal(await picker.choose({platform:'win32',execFile}),path);assert.equal(await picker.choose({platform:'win32',execFile:(e,a,o,cb)=>cb(null,'')}),null);});
test('folder selection surfaces errors',async()=>{assert.throws(()=>picker.choose({platform:'linux'}),/Windows/);await assert.rejects(picker.choose({platform:'win32',execFile:(e,a,o,cb)=>cb(Error('failure'))}),/无法打开/);});
