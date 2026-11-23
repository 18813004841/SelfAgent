const http=require('node:http'), https=require('node:https');
const fs=require('node:fs'), path=require('node:path'), cp=require('node:child_process');
let session=null;
function clearSession(){session=null;}
function request(base, endpoint, {method='GET', body, cookie}={}) {
 return new Promise((resolve,reject)=>{
  const url=new URL(endpoint,base), payload=body===undefined?null:JSON.stringify(body);
  const req=(url.protocol==='https:'?https:http).request(url,{method,timeout:7000,headers:{Accept:'application/json',...(payload?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)}:{}),...(cookie?{Cookie:cookie}:{})}},res=>{
   let data='';res.setEncoding('utf8');res.on('data',x=>{data+=x;if(data.length>1024*1024)req.destroy(new Error('响应过大'));});
   res.on('end',()=>{let json;try{json=JSON.parse(data);}catch{return reject(new Error('工作台返回了无效响应'));}if(res.statusCode<200||res.statusCode>=300||json.ok===false){const e=new Error(json.error||`请求失败 (${res.statusCode})`);e.status=res.statusCode;return reject(e);}resolve({data:json,headers:res.headers});});
  });req.on('timeout',()=>req.destroy(new Error('连接超时')));req.on('error',e=>reject(new Error(e.message==='连接超时'?'连接超时':'无法连接工作台服务器')));if(payload)req.write(payload);req.end();
 });
}
async function authSession(base){if(!session||session.base!==base)return {user:null};try{const r=await request(base,'/api/auth/session',{cookie:session.cookie});if(!r.data.user){clearSession();return {user:null};}return {user:r.data.user};}catch(e){if(e.status===401)clearSession();throw e;}}
async function login(base,args){if(typeof args.username!=='string'||!args.username.trim()||typeof args.password!=='string'||!args.password)throw Error('请输入账号和密码');clearSession();const r=await request(base,'/api/auth/login',{method:'POST',body:{username:args.username.trim(),password:args.password}});const cookie=(r.headers['set-cookie']||[]).map(x=>x.split(';')[0]).find(x=>/^workbench_session=/.test(x));if(!cookie)throw Error('登录失败：服务器未返回会话');session={base,cookie};return {user:r.data.user};}
async function logout(base){const cookie=session?.base===base?session.cookie:null;clearSession();if(cookie)await request(base,'/api/auth/logout',{method:'POST',cookie});return {ok:true};}
async function authenticated(base, endpoint){if(!session||session.base!==base)throw Error('请先登录');try{return (await request(base,endpoint,{cookie:session.cookie})).data;}catch(e){if(e.status===401){clearSession();throw Error('登录已失效，请重新登录');}throw e;}}
async function overview(base){const data=await authenticated(base,'/api/machines');const machine=data.machines?.[0];if(!machine)throw Error('没有可用的机器数据');const details=await authenticated(base,`/api/machine/${encodeURIComponent(machine.machine_id)}/metrics`);return {machine,metrics:details.metrics};}
function command(args){return new Promise((resolve,reject)=>{const isWin=process.platform==='win32', executable=isWin?'powershell.exe':'codex', argv=isWin?['-NoProfile','-NonInteractive','-Command',`codex.cmd ${args.join(' ')}`]:args;cp.execFile(executable,argv,{timeout:20000,windowsHide:true,maxBuffer:1024*1024,encoding:'utf8'},(e,out)=>{if(e)return reject(Error('无法访问本地插件源或更新工具'));resolve(out);});});}
function compareVersions(a,b){const x=a.split('.').map(Number),y=b.split('.').map(Number);for(let i=0;i<3;i++){if(x[i]!==y[i])return x[i]-y[i];}return 0;}
async function updates(version){const data=JSON.parse(await command(['plugin','marketplace','list','--json']));const source=data.marketplaces?.find(x=>x.name==='selfagent-workbench');if(!source?.root)throw Error('未配置插件源');const manifest=JSON.parse(fs.readFileSync(path.join(source.root,'plugins','codex-workbench','.codex-plugin','plugin.json'),'utf8'));const latest=manifest.version;if(!/^\d+\.\d+\.\d+$/.test(latest)||!/^\d+\.\d+\.\d+$/.test(version))throw Error('版本号格式无效');return {current:version,latest,available:compareVersions(latest,version)>0};}
async function installUpdate(version){const info=await updates(version);if(!info.available)throw Error('没有可安装的新版本');await command(['plugin','add','codex-workbench@selfagent-workbench','--json']);return {version:info.latest,message:'安装成功，请重启 Codex 以加载新版本'};}
function openExternal(url){return new Promise((resolve,reject)=>{let executable,args;if(process.platform==='win32'){executable='rundll32.exe';args=['url.dll,FileProtocolHandler',url];}else if(process.platform==='darwin'){executable='open';args=[url];}else{executable='xdg-open';args=[url];}cp.execFile(executable,args,{windowsHide:true,timeout:10000},e=>e?reject(Error('无法打开浏览器，请复制地址')):resolve({opened:true}));});}
module.exports={clearSession,authSession,login,logout,authenticated,overview,updates,installUpdate,openExternal};
