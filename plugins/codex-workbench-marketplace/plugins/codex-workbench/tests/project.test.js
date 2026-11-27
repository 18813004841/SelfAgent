const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const project=require('../features/project');
test('project capability inspection reports missing files and unknown recording state',()=>{const dir=fs.mkdtempSync(path.join(os.tmpdir(),'selfagent-project-'));try{const data=project.inspect(dir);assert.equal(data.trace,false);assert.equal(data.profiler,false);assert.equal(data.bridge,false);assert.equal(data.recording,'unknown');assert.throws(()=>project.inspect('relative'),/绝对路径/);}finally{fs.rmSync(dir,{recursive:true,force:true});}});
