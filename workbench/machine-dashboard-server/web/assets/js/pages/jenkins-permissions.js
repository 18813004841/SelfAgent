const GROUPS = [
  { key: 'overall', label: 'Overall', owners: ['hudson.model.Hudson', 'jenkins.model.Jenkins'], names: ['Overall', '全部', '总体', 'Jenkins'], order: ['Administer', 'Read'] },
  { key: 'credentials', label: 'Credentials', owners: ['com.cloudbees.plugins.credentials.CredentialsProvider'], names: ['Credentials', '凭据'], order: ['Create', 'Delete', 'ManageDomains', 'Update', 'View'] },
  { key: 'agent', label: 'Agent', owners: ['hudson.model.Computer'], names: ['Agent', 'Computer', '代理', '节点'], order: ['Build', 'Configure', 'Connect', 'Create', 'Delete', 'Disconnect', 'Provision'] },
  { key: 'job', label: 'Job', owners: ['hudson.model.Item'], names: ['Job', 'Item', '任务', '作业'], order: ['Build', 'Cancel', 'Configure', 'Create', 'Delete', 'Discover', 'Move', 'Read', 'Workspace'] },
  { key: 'run', label: 'Run', owners: ['hudson.model.Run'], names: ['Run', '运行'], order: ['Delete', 'Replay', 'Update'] },
  { key: 'view', label: 'View', owners: ['hudson.model.View'], names: ['View', '视图'], order: ['Configure', 'Create', 'Delete', 'Read'] },
  { key: 'scm', label: 'SCM', owners: ['hudson.scm.SCM'], names: ['SCM'], order: ['Tag'] },
  { key: 'metrics', label: 'Metrics', owners: ['jenkins.metrics.api.Metrics', 'com.codahale.metrics.MetricRegistry'], names: ['Metrics'], order: ['HealthCheck', 'ThreadDump', 'View'] },
];
export function arrangePermissions(permissions) {
  return permissions.map(permission => {
    const owner = permission.id.slice(0, permission.id.lastIndexOf('.'));
    const name = permission.id.slice(permission.id.lastIndexOf('.') + 1);
    const groupIndex = GROUPS.findIndex(group => group.owners.includes(owner) || group.names.includes(permission.group));
    const definition = GROUPS[groupIndex];
    const order = definition?.order.indexOf(name) ?? -1;
    return {...permission, displayGroup: definition?.label || (/[^\x00-\x7f]/.test(permission.group || '') ? owner.slice(owner.lastIndexOf('.') + 1) : permission.group), displayName: name || permission.name,
      groupRank: groupIndex < 0 ? GROUPS.length : groupIndex, permissionRank: order < 0 ? Number.MAX_SAFE_INTEGER : order};
  }).sort((a, b) => a.groupRank - b.groupRank || a.displayGroup.localeCompare(b.displayGroup) || a.permissionRank - b.permissionRank || a.id.localeCompare(b.id));
}

export function mountPermissions(scope) {
  const registerTab = document.querySelector('#jenkins-register-tab'), permissionTab = document.querySelector('#jenkins-permissions-tab'),
    registerPanel = document.querySelector('#jenkins-register-panel'), panel = document.querySelector('#jenkins-permissions-panel'),
    form = document.querySelector('#jenkins-permissions-search'), input = document.querySelector('#jenkins-permissions-username'),
    message = document.querySelector('#jenkins-permissions-message'), results = document.querySelector('#jenkins-permissions-results'),
    profileMessage = document.querySelector('#jenkins-profile-message'), refresh = document.querySelector('#jenkins-profile-refresh');
  const levels = ['qa', 'admin'];
  const cards = new Map();
  let catalogLoaded = false, loading = false, searching = false, selectedUser = '', catalogPromise = null;
  const copy = values => new Set(values || []);
  const same = (a, b) => a.size === b.size && [...a].every(value => b.has(value));
  const sorted = set => [...set].sort();
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, className, handler) {
    const node = element('button', text, className); node.type = 'button'; node.onclick = handler; return node;
  }
  function setTab(active) {
    registerTab.setAttribute('aria-selected', String(!active)); permissionTab.setAttribute('aria-selected', String(active));
    registerPanel.hidden = active; panel.hidden = !active;
  }
  registerTab.onclick = () => setTab(false);
  permissionTab.onclick = () => { setTab(true); if (!catalogLoaded && !loading) catalogPromise = loadCatalog(); };
  refresh.onclick = () => { if (!loading && !searching && ![...cards.values()].some(card => card.busy) && confirmDiscard('刷新列表')) catalogPromise = loadCatalog(); };
  async function request(path, body) {
    const response = await scope.fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `请求失败 (${response.status})`);
    return data;
  }
  const strategyOf = item => item.roleBased ? 'roles' : 'matrix';
  function optionsFor(item) {
    return item.roleBased ? (item.availableRoles || []).map(id => ({id, group:id.startsWith('globalRoles:') ? 'Global roles' : 'Item roles', label:id.startsWith('globalRoles:') ? id.slice(12) : id.slice(13)})) :
      arrangePermissions(item.permissions || []).map(p => ({id:p.id, group:p.displayGroup, label:p.displayName}));
  }
  function profileValues(item) {
    const config = item.profileConfig?.strategy === strategyOf(item) ? item.profileConfig.profiles : null;
    return Object.fromEntries(levels.map(level => [level, copy(config?.[level])]));
  }
  function newCard(item, index) {
    const original = profileValues(item);
    return {item, index, open:index === 0, mode:'profiles', user:null, userBase:new Set(), userDraft:new Set(),
      profileBase:original, profileDraft:Object.fromEntries(levels.map(level => [level, copy(original[level])])),
      choice:'current', busy:false, userStatus:'', profileStatus:''};
  }
  function userDirty(card) { return !!card.user && !same(card.userBase, card.userDraft); }
  function profileDirty(card) { return levels.some(level => !same(card.profileBase[level], card.profileDraft[level])); }
  function confirmDiscard(action, includeProfiles=true) {
    const dirty = [...cards.values()].some(card => userDirty(card) || (includeProfiles && profileDirty(card)));
    return !dirty || window.confirm(`${action}会丢弃未保存的更改，是否继续？`);
  }
  function userReady(card) {
    const item = card.user;
    return !!item && !item.error && item.registered === true && !item.ambiguous && (!item.roleBased || item.roleEditable);
  }
  function userProblem(card) {
    const item = card.user;
    if (!item) return '请先搜索用户';
    if (item.error) return `查询失败：${item.error}`;
    if (item.registered === false) return '用户未注册';
    if (item.registered !== true) return '无法确认用户是否注册';
    if (item.ambiguous) return '旧权限项类型不明确，请在 Jenkins 中处理';
    if (item.roleBased && !item.roleEditable) return '当前身份源不支持修改角色';
    return '';
  }
  function currentMeta(card) { return card.user && !card.user.error ? card.user : card.item; }
  function renderAll() {
    results.replaceChildren();
    for (const card of cards.values()) results.append(renderCard(card));
  }
  function renderCard(card) {
    const meta = currentMeta(card), strategy = strategyOf(meta), options = optionsFor(meta), optionIds = new Set(options.map(option => option.id));
    const container = element('details', undefined, 'jenkins-access-card'); container.open = card.open;
    container.ontoggle = () => { card.open = container.open; };
    const summary = element('summary', undefined, 'jenkins-access-summary');
    summary.append(element('strong', `Jenkins ${meta.ip}`));
    const badges = [];
    if (card.item.error) badges.push(`配置读取失败：${card.item.error}`);
    else badges.push(strategy === 'roles' ? '角色授权' : '矩阵授权');
    if (userDirty(card)) badges.push('用户权限未保存');
    if (profileDirty(card)) badges.push('方案未保存');
    summary.append(element('span', badges.join(' · '), 'jenkins-access-summary-note')); container.append(summary);
    const content = element('div', undefined, 'jenkins-access-content'); container.append(content);
    if (card.item.error && !card.user) { content.append(element('p', `读取失败：${card.item.error}。请刷新 Jenkins 列表。`)); return container; }
    const nav = element('div', undefined, 'jenkins-access-nav'); nav.setAttribute('role', 'group'); nav.setAttribute('aria-label', `${meta.ip} 编辑内容`);
    for (const [mode, label] of [['user','用户权限'], ['profiles','方案配置']]) {
      const tab = button(label, `jenkins-access-tab${card.mode === mode ? ' is-active' : ''}`, () => { card.mode = mode; renderAll(); });
      tab.setAttribute('aria-pressed', String(card.mode === mode)); nav.append(tab);
    }
    content.append(nav);
    const notice = element('p', '', 'jenkins-access-notice'); notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
    if (card.mode === 'user') renderUser(card, content, notice, options, optionIds);
    else renderProfiles(card, content, notice, options, optionIds);
    content.append(notice);
    return container;
  }
  function renderTable(card, options, rows, disabled, onChange) {
    const wrapper = element('div', undefined, 'jenkins-matrix-scroll'), table = element('table', undefined, 'jenkins-profile-table jenkins-profile-config');
    table.append(element('caption', `${currentMeta(card).ip} ${card.mode === 'user' ? '用户权限' : '权限方案配置'}`));
    const groupRow = element('tr'), headings = element('tr'), rowHeader = element('th', card.mode === 'user' ? '用户' : '方案');
    rowHeader.scope='col'; rowHeader.rowSpan=2; groupRow.append(rowHeader);
    for (let index=0; index<options.length;) {
      let end=index+1; while (end<options.length && options[end].group===options[index].group) end++;
      const group=element('th', options[index].group); group.scope='colgroup'; group.colSpan=end-index; groupRow.append(group);
      for (const option of options.slice(index,end)) {
        const label=element('th',option.label,'jenkins-profile-parameter'); label.scope='col'; label.title=option.id; headings.append(label);
      }
      index=end;
    }
    const head=element('thead'); head.append(groupRow,headings); table.append(head);
    const body=element('tbody'), inputs=[];
    for (const row of rows) {
      const tr=element('tr'), label=element('th',row.label); label.scope='row'; tr.append(label);
      for (const option of options) {
        const td=element('td'), box=element('input'); box.type='checkbox'; box.checked=row.values.has(option.id); box.disabled=disabled;
        box.setAttribute('aria-label', `${currentMeta(card).ip} ${row.label} ${option.group} ${option.label}`);
        box.onchange=()=>{ if (box.checked) row.values.add(option.id); else row.values.delete(option.id); onChange(); };
        inputs.push({box,row:row.label,id:option.id}); td.append(box); tr.append(td);
      }
      body.append(tr);
    }
    table.append(body); wrapper.append(table); return {wrapper, inputs};
  }
  function renderUser(card, content, notice, options, optionIds) {
    const problem=userProblem(card), controls=element('div', undefined, 'jenkins-access-controls');
    const label=element('span', '填充方案', 'jenkins-access-label'); controls.append(label);
    const choices=element('div',undefined,'jenkins-access-choices'); choices.setAttribute('role','group'); choices.setAttribute('aria-label',`${card.item.ip} 权限填充`);
    const optionConfig=card.user?.profileConfig?.strategy===strategyOf(card.user) ? card.user.profileConfig.profiles : null;
    for (const [value, text] of [['current','当前'],['qa','qa'],['admin','admin']]) {
      const choice=button(text,`jenkins-access-choice${card.choice===value?' is-active':''}`,()=>{
        card.userDraft = value==='current' ? copy(card.userBase) : copy(optionConfig[value]); card.choice=value; card.userStatus=''; renderAll();
      });
      choice.setAttribute('aria-pressed',String(card.choice===value));
      choice.disabled=card.busy || !userReady(card) || (value!=='current' && (!optionConfig?.[value]?.length || optionConfig[value].some(id=>!optionIds.has(id))));
      choices.append(choice);
    }
    controls.append(choices, element('span','选择方案填充，勾选可单独修改','jenkins-access-help'));
    const save=button('保存用户权限','primary jenkins-access-save',async()=>{
      if (!userReady(card) || card.busy || !userDirty(card)) return;
      card.busy=true; card.userStatus='正在保存用户权限...'; renderAll();
      try {
        const data=await request('/api/jenkins/permissions/save',{ip:card.item.ip,username:selectedUser,revision:card.user.revision,strategy:strategyOf(card.user),selection:sorted(card.userDraft)});
        if (!data.result?.saved || !/^[a-f0-9]{64}$/.test(data.result.revision || '')) throw new Error('保存结果无法确认，请重新搜索');
        card.user.revision=data.result.revision; card.item.revision=data.result.revision;
        card.userBase=copy(card.userDraft); card.choice='current'; card.userStatus='用户权限已保存';
      } catch(error) { card.userStatus=`保存失败：${error.message}。如请求超时，请重新搜索确认结果。`; }
      finally { card.busy=false; renderAll(); }
    });
    save.disabled=card.busy || !userReady(card) || !userDirty(card); controls.append(save); content.append(controls);
    if (problem) content.append(element('p',problem,'jenkins-access-help'));
    if (strategyOf(currentMeta(card))==='roles') content.append(element('p','角色名称可能同时匹配同名用户和用户组；用户组等其他授权可能另行生效。','jenkins-access-help'));
    if (!options.length) { content.append(element('p','未返回可配置权限')); notice.textContent=card.userStatus; return; }
    const table=renderTable(card,options,[{label:selectedUser || '用户',values:card.userDraft}],card.busy || !userReady(card),()=>{
      card.choice = same(card.userDraft,card.userBase) ? 'current' : 'custom'; card.userStatus='';
      notice.textContent=userDirty(card) ? '有未保存的用户权限更改' : '与当前用户权限一致';
      save.disabled=card.busy || !userReady(card) || !userDirty(card);
      choices.querySelectorAll('button').forEach(node=>node.classList.remove('is-active'));
      if (card.choice==='current') { const current=choices.querySelector('button'); current.classList.add('is-active'); }
      choices.querySelectorAll('button').forEach(node=>node.setAttribute('aria-pressed',String(card.choice==='current' && node.textContent==='当前')));
    });
    content.append(table.wrapper);
    notice.textContent=card.userStatus || (problem ? '' : userDirty(card) ? '有未保存的用户权限更改' : '与当前用户权限一致');
  }
  function renderProfiles(card, content, notice, options, optionIds) {
    const meta=currentMeta(card), editable=!card.item.error && (!meta.roleBased || meta.roleEditable);
    const controls=element('div',undefined,'jenkins-access-controls');
    controls.append(element('span','配置此 Jenkins 的 qa 和 admin 方案','jenkins-access-help'));
    const save=button('保存方案配置','primary jenkins-access-save',async()=>{
      if (!editable || card.busy || !profileDirty(card)) return;
      card.busy=true; card.profileStatus='正在保存方案...'; renderAll();
      try {
        const profiles=Object.fromEntries(levels.map(level=>[level,sorted(card.profileDraft[level])]));
        const data=await request('/api/jenkins/permissions/profiles',{ip:card.item.ip,revision:card.item.revision,profileRevision:card.item.profileConfig?.revision || null,profiles});
        if (!data.result?.saved || !/^[a-f0-9]{64}$/.test(data.result.revision || '')) throw new Error('保存结果无法确认，请刷新列表');
        const profileConfig={strategy:strategyOf(meta),profiles,revision:data.result.revision};
        card.item.profileConfig=profileConfig; if(card.user) card.user.profileConfig=profileConfig;
        card.profileBase=Object.fromEntries(levels.map(level=>[level,copy(card.profileDraft[level])]));
        card.profileStatus='方案配置已保存';
      } catch(error) { card.profileStatus=`保存失败：${error.message}`; }
      finally { card.busy=false; renderAll(); }
    });
    save.disabled=card.busy || !editable || !profileDirty(card); controls.append(save); content.append(controls);
    if (meta.roleBased) content.append(element('p','角色名称可能同时匹配同名用户和用户组。','jenkins-access-help'));
    if (!options.length || !editable) { content.append(element('p',card.item.error || (!options.length ? '未返回可配置项' : '当前身份源不支持修改角色'))); notice.textContent=card.profileStatus; return; }
    const table=renderTable(card,options,levels.map(level=>({label:level,values:card.profileDraft[level]})),card.busy,()=>{
      card.profileStatus=''; notice.textContent=profileDirty(card) ? '有未保存的方案更改' : '方案配置无更改'; save.disabled=card.busy || !profileDirty(card);
    });
    content.append(table.wrapper);
    const obsolete=levels.flatMap(level=>[...card.profileDraft[level]].filter(id=>!optionIds.has(id)).map(id=>`${level}: ${id}`));
    if (obsolete.length) {
      content.append(element('p',`已保存但 Jenkins 当前不显示的权限：${obsolete.join('、')}。请先刷新或在 Jenkins 中处理，无法直接保存。`,'jenkins-access-warning'));
      const remove = button('移除不可用项', 'jenkins-access-remove', () => {
        for (const level of levels) for (const id of card.profileDraft[level]) if (!optionIds.has(id)) card.profileDraft[level].delete(id);
        card.profileStatus='已移除不可用项，请保存方案'; renderAll();
      });
      remove.disabled = card.busy; content.append(remove);
      save.disabled=true;
      table.inputs.forEach(({box})=>{const change=box.onchange; box.onchange=()=>{change(); save.disabled=true;};});
    }
    notice.textContent=card.profileStatus || (profileDirty(card) ? '有未保存的方案更改' : '方案配置无更改');
  }
  async function loadCatalog() {
    loading=true; refresh.disabled=true; profileMessage.textContent='正在加载 Jenkins...';
    try {
      const data=await request('/api/jenkins/permissions/catalog',{});
      cards.clear(); data.results.forEach((item,index)=>cards.set(item.ip,newCard(item,index)));
      catalogLoaded=true; selectedUser=''; results.replaceChildren(); message.textContent='';
      profileMessage.textContent=data.results.length ? '' : '暂无 Jenkins'; renderAll();
    } catch(error) { profileMessage.textContent=`加载失败：${error.message}`; }
    finally { loading=false; refresh.disabled=false; }
  }
  form.onsubmit=async event=>{
    event.preventDefault(); const username=input.value.trim();
    if (!username || searching || [...cards.values()].some(card => card.busy) || !confirmDiscard('搜索其他用户',false)) return;
    searching=true; form.querySelector('button').disabled=true; message.textContent='正在查询...';
    try {
      if (catalogPromise) await catalogPromise;
      const data=await request('/api/jenkins/permissions/search',{username}); selectedUser=username;
      for (const card of cards.values()) { card.user=null; card.userBase=new Set(); card.userDraft=new Set(); card.userStatus=''; }
      for (const [index,item] of data.results.entries()) {
        let card=cards.get(item.ip);
        if (!card) { card=newCard(item,index); cards.set(item.ip,card); }
        if (!item.error && !profileDirty(card)) {
          card.item=item; card.profileBase=profileValues(item);
          card.profileDraft=Object.fromEntries(levels.map(level=>[level,copy(card.profileBase[level])]));
        }
        card.user=item; card.userBase=copy(item.roleBased ? item.assignedRoles : item.granted); card.userDraft=copy(card.userBase);
        card.choice='current'; card.mode='user'; card.userStatus='';
      }
      message.textContent=data.results.length ? `用户 ${username} 的查询结果` : '暂无 Jenkins'; renderAll();
    } catch(error) { message.textContent=`查询失败：${error.message}`; }
    finally { searching=false; form.querySelector('button').disabled=false; }
  };
}
