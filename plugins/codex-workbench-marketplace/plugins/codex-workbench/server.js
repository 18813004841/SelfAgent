const readline = require('node:readline');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const https = require('node:https');
const adapter = require('./adapter');
const URI = 'ui://selfagent/workbench';
const mimeType = 'text/html;profile=mcp-app';
const DEFAULT_URL = 'http://10.0.76.228:18888/';
const configDir = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'LocalWorkbench', 'codex-plugin') : path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'LocalWorkbench', 'codex-plugin');
const configFile = path.join(configDir, 'settings.json');
const version = JSON.parse(fs.readFileSync(path.join(__dirname, '.codex-plugin', 'plugin.json'), 'utf8')).version;
const icon = 'data:image/png;base64,' + fs.readFileSync(path.join(__dirname, 'assets', 'koa.png')).toString('base64');
const appOnly = {ui:{visibility:['app']}};
const tools = [
 {icons:[{src:icon,mimeType:'image/png',sizes:['256x256']}],name:'open_workbench',title:'KOA工作台',description:'打开KOA工作台界面。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,destructiveHint:false,openWorldHint:false},_meta:{ui:{resourceUri:URI},'openai/ui':{entrypoints:[{type:'global'}]}}},
 {name:'get_workbench_settings',description:'读取工作台服务器地址。',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},_meta:appOnly},
 {name:'save_workbench_settings',description:'保存工作台服务器地址。',inputSchema:{type:'object',properties:{url:{type:'string'}},required:['url'],additionalProperties:false},_meta:appOnly},
 ...[
  ['workbench_session','查询登录状态',{}],
  ['workbench_login','登录工作台',{username:{type:'string'},password:{type:'string'}}],
  ['workbench_logout','退出工作台',{}],
  ['workbench_overview','读取机器概览',{}],
  ['workbench_schedules','读取定时任务',{}],
  ['workbench_open_external','在浏览器打开工作台',{}],
  ['workbench_check_updates','检查插件更新',{}],
  ['workbench_install_update','安装插件更新',{}]
 ].map(([name,description,properties])=>({name,description,inputSchema:{type:'object',properties,additionalProperties:false},_meta:appOnly})),
 {name:'test_workbench_connection',description:'检查工作台服务器连接。',inputSchema:{type:'object',properties:{url:{type:'string'}},required:['url'],additionalProperties:false},annotations:{readOnlyHint:true},_meta:appOnly}
];
function normalize(value) {
 if(typeof value !== 'string' || value.length > 2048) throw new Error('请输入有效的服务器地址');
 let u; try { u = new URL(value.trim()); } catch { throw new Error('请输入有效的服务器地址'); }
 if (!['http:','https:'].includes(u.protocol) || u.username || u.password || u.pathname !== '/' || u.search || u.hash) throw new Error('请输入以 http:// 或 https:// 开头的服务器根地址，不包含账号、路径或参数');
 return u.origin + '/';
}
function readConfig() {
 try { const config=JSON.parse(fs.readFileSync(configFile,'utf8')); return normalize(config.url); }
 catch(e) { if(e.code==='ENOENT') return DEFAULT_URL; throw new Error('无法读取服务器配置，请检查配置文件'); }
}
function saveConfig(url) {
 const old = readConfig();
 fs.mkdirSync(configDir,{recursive:true});
 const temp = path.join(configDir, `settings.${process.pid}.tmp`);
 try { fs.writeFileSync(temp,JSON.stringify({url},null,2)+'\n',{mode:0o600}); fs.renameSync(temp,configFile); }
 finally { try { fs.unlinkSync(temp); } catch(e) { if(e.code!=='ENOENT') throw e; } }
 if(old!==url) adapter.clearSession();
 return {url,changed:old!==url};
}
function testConnection(url) {
 return new Promise((resolve,reject)=>{
  const target=new URL('/api/auth/session',url);
  const req=(target.protocol==='https:'?https:http).get(target,{headers:{Accept:'application/json'},timeout:5000},res=>{
   let body=''; res.setEncoding('utf8'); res.on('data',chunk=>{body+=chunk;if(body.length>65536)req.destroy(new Error('响应过大'));});
   res.on('end',()=>{try { const data=JSON.parse(body); if(res.statusCode!==200 || data.ok!==true || !Object.prototype.hasOwnProperty.call(data,'user') || !data.modules || typeof data.modules !== 'object' || Array.isArray(data.modules)) throw new Error(); resolve({url,reachable:true}); } catch {reject(new Error('服务响应不符合工作台接口'));}});
  });
  req.on('timeout',()=>req.destroy(new Error('连接超时'))); req.on('error',e=>reject(new Error(e.message==='连接超时'?'连接超时':'无法连接工作台服务器')));
 });
}
const response = data => ({content:[{type:'text',text:JSON.stringify(data)}]});
async function result(m) {
 switch(m.method) {
 case 'initialize': return {protocolVersion:m.params?.protocolVersion || '2025-03-26',capabilities:{tools:{},resources:{}},serverInfo:{name:'custom-workbench',version}};
 case 'ping': return {};
 case 'tools/list': return {tools};
 case 'resources/list': return {resources:[{uri:URI,name:'KOA工作台',mimeType}]};
 case 'resources/read': if(m.params?.uri !== URI) throw {code:-32602,message:'Unknown resource'}; return {contents:[{uri:URI,mimeType,text:fs.readFileSync(path.join(__dirname,'workbench.html'),'utf8')}]};
 case 'tools/call': {
  const {name,arguments:args={}}=m.params||{};
  try {
   if(name==='open_workbench') return response({message:'KOA工作台已准备就绪'});
   if(name==='workbench_session') return response(await adapter.authSession(readConfig()));
   if(name==='workbench_login') return response(await adapter.login(readConfig(),args));
   if(name==='workbench_logout') return response(await adapter.logout(readConfig()));
   if(name==='workbench_overview') return response(await adapter.overview(readConfig()));
   if(name==='workbench_schedules') return response(await adapter.authenticated(readConfig(),'/api/scheduler-tasks'));
   if(name==='workbench_open_external') return response(await adapter.openExternal(readConfig()));
   if(name==='workbench_check_updates') return response(await adapter.updates(version));
   if(name==='workbench_install_update') return response(await adapter.installUpdate(version));
   if(name==='get_workbench_settings') return response({url:readConfig(),version});
   if(name==='save_workbench_settings') return response(saveConfig(normalize(args.url)));
   if(name==='test_workbench_connection') return response(await testConnection(normalize(args.url)));
   throw {code:-32602,message:'Unknown tool'};
  } catch(e) {if(e.code===-32602)throw e; return {isError:true,content:[{type:'text',text:e.message||'操作失败'}]};}
 }
 default: throw {code:-32601,message:'Method not found'};
 }
}
readline.createInterface({input:process.stdin,crlfDelay:Infinity}).on('line',async line=>{let m;try{m=JSON.parse(line);if(m.id===undefined)return; process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,result:await result(m)})+'\n');}catch(e){if(m?.id!==undefined)process.stdout.write(JSON.stringify({jsonrpc:'2.0',id:m.id,error:{code:e.code||-32603,message:e.message||'Internal error'}})+'\n');}});
