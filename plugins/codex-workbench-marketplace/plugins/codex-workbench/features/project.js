const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const configDir = process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, 'SelfAgent', 'codex-plugin') : path.join(process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config'), 'selfagent', 'codex-plugin');
const configFile = path.join(configDir, 'analysis.json');
function inspect(input) {
 if (typeof input !== 'string' || !path.isAbsolute(input)) throw Error('请输入工程绝对路径');
 let root; try { root = fs.realpathSync(input); if (!fs.statSync(root).isDirectory()) throw Error(); } catch { throw Error('工程目录不存在或无法访问'); }
 const game = path.join(root, 'Game');
 const has = p => { try { return fs.statSync(p).isFile(); } catch { return false; } };
 const trace = has(path.join(game, 'Tools', 'UnityTracepoint', 'capture.py')) && has(path.join(game, 'Tools', 'UnityTracepoint', 'server.py'));
 const profiler = has(path.join(game, 'Tools', 'UnityTracepoint', 'profiler_watch.py'));
 const bridge = has(path.join(game, 'Assets', 'Editor', 'ProfilerAnalysis', 'ProfileData', 'ProfilerWatchBridge.cs'));
 const editorInstance = has(path.join(game, 'Library', 'EditorInstance.json'));
 return {root, trace, profiler, bridge, editorInstance, recording:'unknown'};
}
function save(root) { const result=inspect(root); fs.mkdirSync(configDir,{recursive:true}); const tmp=configFile+'.'+process.pid+'.tmp'; try { fs.writeFileSync(tmp,JSON.stringify({root:result.root}),{mode:0o600}); fs.renameSync(tmp,configFile); } finally { try { fs.unlinkSync(tmp); } catch(e) { if(e.code!=='ENOENT') throw e; } } return result; }
function load() { let data; try {data=JSON.parse(fs.readFileSync(configFile,'utf8'));} catch(e) {if(e.code==='ENOENT')return null; throw Error('无法读取工程绑定配置');} return inspect(data.root); }
module.exports={inspect,save,load};
