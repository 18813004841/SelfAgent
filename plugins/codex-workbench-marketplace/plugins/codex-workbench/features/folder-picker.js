const cp = require('node:child_process');
const script = `Add-Type -AssemblyName System.Windows.Forms
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '选择工程根目录'
$dialog.ShowNewFolderButton = $false
try {
 if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::WriteLine([Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($dialog.SelectedPath)))
 }
} finally { $dialog.Dispose() }`;
function choose(options = {}) {
 if ((options.platform || process.platform) !== 'win32') throw Error('当前仅支持在 Windows 选择文件夹，请手动输入目录');
 const run = options.execFile || cp.execFile;
 return new Promise((resolve, reject) => {
  run('powershell.exe',['-NoProfile','-STA','-EncodedCommand',Buffer.from(script,'utf16le').toString('base64')],{windowsHide:true,timeout:300000,encoding:'utf8',maxBuffer:16384},(err,out)=>{
   if(err) return reject(Error('无法打开文件夹选择窗口，请手动输入目录'));
   const value=out.trim();
   if(!value) return resolve(null);
   try { const result=Buffer.from(value,'base64').toString('utf8'); if(!result || Buffer.from(result,'utf8').toString('base64')!==value) throw Error(); resolve(result); }
   catch { reject(Error('无法读取选择的目录')); }
  });
 });
}
module.exports={choose,script};
