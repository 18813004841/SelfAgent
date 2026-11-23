const {test}=require('node:test');
const assert=require('node:assert/strict');
const http=require('node:http');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
const {spawn}=require('node:child_process');
const readline=require('node:readline');
const root=path.resolve(__dirname,'..');

test('session isolation, overview, expiration and server change',async()=>{
 let valid=true;
 const server=http.createServer((req,res)=>{
  const send=(status,value,headers={})=>{res.writeHead(status,{'content-type':'application/json',...headers});res.end(JSON.stringify(value));};
  if(req.method==='POST'&&req.url==='/api/auth/login'){
   let body='';req.on('data',x=>body+=x);req.on('end',()=>{const input=JSON.parse(body);if(input.password!=='sample-password')return send(401,{ok:false,error:'用户名或密码错误'});send(200,{ok:true,user:{username:'test'}},{'set-cookie':'workbench_session=fixture-token; HttpOnly; Path=/'});});return;
  }
  if(req.url==='/api/auth/session')return send(200,{ok:true,user:req.headers.cookie==='workbench_session=fixture-token'&&valid?{username:'test'}:null,modules:{overview:'总览'}});
  if(req.headers.cookie!=='workbench_session=fixture-token'||!valid)return send(401,{ok:false,error:'请先登录'});
  if(req.url==='/api/machines')return send(200,{ok:true,machines:[{machine_id:'machine',hostname:'fixture',os:'test'}]});
  if(req.url==='/api/machine/machine/metrics')return send(200,{ok:true,metrics:{memory:{percent:81},disks:[],ips:[]}});
  if(req.url==='/api/scheduler-tasks')return send(200,{ok:true,tasks:[{name:'fixture-task'}]});
  if(req.url==='/api/auth/logout')return send(200,{ok:true});
  return send(404,{ok:false,error:'not found'});
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'koa-plugin-test-'));
 const child=spawn(process.execPath,['server.js'],{cwd:root,env:{...process.env,LOCALAPPDATA:temp},stdio:['pipe','pipe','pipe']});
 const lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator]();let next=0;
 async function call(name,args={}){const id=++next;child.stdin.write(JSON.stringify({jsonrpc:'2.0',id,method:'tools/call',params:{name,arguments:args}})+'\n');const {value}=await lines.next();const response=JSON.parse(value);assert.equal(response.id,id);return response.result;}
 const data=result=>JSON.parse(result.content[0].text);
 try{
  const base=`http://127.0.0.1:${server.address().port}/`;
  assert.equal(data(await call('get_workbench_settings')).version,JSON.parse(fs.readFileSync(path.join(root,'.codex-plugin','plugin.json'),'utf8')).version);
  assert.equal((await call('save_workbench_settings',{url:'http://name:password@example.com/'})).isError,true);
  assert.equal(data(await call('save_workbench_settings',{url:base})).changed,true);
  assert.equal(data(await call('workbench_session')).user,null);
  assert.equal((await call('workbench_login',{username:'test',password:'wrong'})).isError,true);
  const login=await call('workbench_login',{username:'test',password:'sample-password'});
  assert.equal(data(login).user.username,'test');assert.doesNotMatch(JSON.stringify(login),/fixture-token|sample-password/);
  assert.equal(data(await call('workbench_overview')).metrics.memory.percent,81);
  assert.equal(data(await call('workbench_schedules')).tasks[0].name,'fixture-task');
  valid=false;assert.match((await call('workbench_overview')).content[0].text,/登录已失效/);assert.equal(data(await call('workbench_session')).user,null);
  valid=true;await call('workbench_login',{username:'test',password:'sample-password'});
  assert.equal(data(await call('save_workbench_settings',{url:'http://localhost:12345/'})).changed,true);assert.equal(data(await call('workbench_session')).user,null);
  const saved=fs.readFileSync(path.join(temp,'LocalWorkbench','codex-plugin','settings.json'),'utf8');assert.doesNotMatch(saved,/fixture-token|sample-password/);
 }finally{
  child.kill();await new Promise(resolve=>child.once('exit',resolve));await new Promise(resolve=>server.close(resolve));
  const resolved=fs.realpathSync(temp), tempRoot=fs.realpathSync(os.tmpdir());if(path.dirname(resolved)!==tempRoot||!path.basename(resolved).startsWith('koa-plugin-test-'))throw Error('unsafe temporary test path');fs.rmSync(resolved,{recursive:true,force:true});
 }
});
