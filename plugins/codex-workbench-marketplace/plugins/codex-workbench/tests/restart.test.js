const {test}=require('node:test');
const assert=require('node:assert/strict');
const {EventEmitter}=require('node:events');
const {PassThrough}=require('node:stream');
const {restart,script}=require('../features/restart');
function fake(line){return ()=>{const c=new EventEmitter();c.stdout=new PassThrough();c.unref=()=>{};c.kill=()=>{};process.nextTick(()=>c.stdout.write(line+'\n'));return c;};}
test('restart waits for helper preflight',async()=>{assert.match((await restart({platform:'win32',spawn:fake('READY')})).message,/已就绪/);assert.match(script,/OpenAI\\\.Codex/);});
test('restart reports preflight and platform errors',async()=>{assert.throws(()=>restart({platform:'linux'}),/Windows/);await assert.rejects(restart({platform:'win32',spawn:fake('ERROR: CIM denied')}),/CIM denied/);});
