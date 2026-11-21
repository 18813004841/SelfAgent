const GROUPS = [
  { key: 'overall', label: '全部', owners: ['hudson.model.Hudson', 'jenkins.model.Jenkins'], names: ['Overall', '全部', '总体', 'Jenkins'], order: ['Administer', 'Read'] },
  { key: 'credentials', label: '凭据', owners: ['com.cloudbees.plugins.credentials.CredentialsProvider'], names: ['Credentials', '凭据'], order: ['Create', 'Delete', 'ManageDomains', 'Update', 'View'] },
  { key: 'agent', label: '代理', owners: ['hudson.model.Computer'], names: ['Agent', 'Computer', '代理', '节点'], order: ['Build', 'Configure', 'Connect', 'Create', 'Delete', 'Disconnect', 'Provision'] },
  { key: 'job', label: '任务', owners: ['hudson.model.Item'], names: ['Job', 'Item', '任务', '作业'], order: ['Build', 'Cancel', 'Configure', 'Create', 'Delete', 'Discover', 'Move', 'Read', 'Workspace'] },
  { key: 'run', label: '运行', owners: ['hudson.model.Run'], names: ['Run', '运行'], order: ['Delete', 'Replay', 'Update'] },
  { key: 'view', label: '视图', owners: ['hudson.model.View'], names: ['View', '视图'], order: ['Configure', 'Create', 'Delete', 'Read'] },
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
    return {...permission, displayGroup: definition?.label || permission.group, displayName: name || permission.name,
      groupRank: groupIndex < 0 ? GROUPS.length : groupIndex, permissionRank: order < 0 ? Number.MAX_SAFE_INTEGER : order};
  }).sort((a, b) => a.groupRank - b.groupRank || a.displayGroup.localeCompare(b.displayGroup) || a.permissionRank - b.permissionRank || a.id.localeCompare(b.id));
}

export function mountPermissions(scope) {
  const registerTab = document.querySelector('#jenkins-register-tab'), permissionTab = document.querySelector('#jenkins-permissions-tab'),
    registerPanel = document.querySelector('#jenkins-register-panel'), panel = document.querySelector('#jenkins-permissions-panel'),
    form = document.querySelector('#jenkins-permissions-search'), input = document.querySelector('#jenkins-permissions-username'),
    message = document.querySelector('#jenkins-permissions-message'), results = document.querySelector('#jenkins-permissions-results');
  function selectPermissions(active) {
    registerTab.setAttribute('aria-selected', String(!active)); permissionTab.setAttribute('aria-selected', String(active));
    registerPanel.hidden = active; panel.hidden = !active;
  }
  registerTab.onclick = () => selectPermissions(false);
  permissionTab.onclick = () => selectPermissions(true);
  async function request(path, body) {
    const response = await scope.fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    const data = await response.json(); if (!response.ok || !data.ok) throw new Error(data.error || `请求失败 (${response.status})`); return data;
  }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function renderMatrix(items, username) {
    const permissions = new Map();
    for (const item of items) for (const permission of item.permissions || []) {
      if (!permissions.has(permission.id)) permissions.set(permission.id, permission);
    }
    const columns = arrangePermissions([...permissions.values()]);
    const wrapper = element('div', undefined, 'jenkins-matrix-scroll');
    const table = element('table', undefined, 'jenkins-matrix');
    const caption = element('caption', `用户 ${username} 的全局权限`); table.append(caption);
    const head = element('thead'), groupRow = element('tr'), permissionRow = element('tr');
    const serverHeader = element('th', 'Jenkins / 状态', 'jenkins-matrix-server'); serverHeader.rowSpan = 2; serverHeader.scope = 'col'; groupRow.append(serverHeader);
    for (let index = 0; index < columns.length;) {
      let end = index + 1; while (end < columns.length && columns[end].displayGroup === columns[index].displayGroup) end++;
      const th = element('th', columns[index].displayGroup); th.colSpan = end - index; th.scope = 'colgroup'; groupRow.append(th);
      for (const column of columns.slice(index, end)) {
        const label = element('th', column.displayName, 'jenkins-matrix-permission'); label.scope = 'col'; label.title = column.id; permissionRow.append(label);
      }
      index = end;
    }
    const actionHeader = element('th', '操作'); actionHeader.rowSpan = 2; actionHeader.scope = 'col'; groupRow.append(actionHeader);
    head.append(groupRow, permissionRow); table.append(head);
    const body = element('tbody');
    for (const item of items) {
      const row = element('tr'); const identity = element('th', undefined, 'jenkins-matrix-server'); identity.scope = 'row';
      const name = element('strong', item.ip), state = element('span', '', 'jenkins-matrix-status');
      state.setAttribute('role', 'status'); state.setAttribute('aria-live', 'polite'); identity.append(name, state); row.append(identity);
      const supported = new Set((item.permissions || []).map(permission => permission.id));
      const selectable = !item.error && item.registered === true && !item.ambiguous;
      state.textContent = item.error || (item.registered === false ? '未注册' : item.registered !== true ? '无法确认是否注册' : item.ambiguous ? '旧权限项类型不明确，请在 Jenkins 中处理' : '已注册');
      for (const permission of columns) {
        const cell = element('td', undefined, 'jenkins-matrix-cell');
        if (supported.has(permission.id) && item.registered === true && !item.error) {
          const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.value = permission.id;
          checkbox.checked = (item.granted || []).includes(permission.id); checkbox.disabled = !selectable;
          checkbox.setAttribute('aria-label', `${item.ip} ${permission.displayGroup} ${permission.displayName}`); cell.append(checkbox);
        } else { cell.textContent = '—'; cell.title = item.error || (item.registered === true ? '此 Jenkins 不支持此权限' : '无可用权限数据'); }
        row.append(cell);
      }
      const actions = element('td', undefined, 'jenkins-matrix-actions');
      if (selectable) {
        const save = element('button', '保存', 'primary'); save.type = 'button';
        save.onclick = async () => {
          const checkboxes = [...row.querySelectorAll('input')];
          const permissions = checkboxes.filter(el => el.checked).map(el => el.value);
          save.disabled = true; checkboxes.forEach(el => { el.disabled = true; }); state.textContent = '正在保存...';
          try {
            const data = await request('/api/jenkins/permissions/save', {ip:item.ip, username, revision:item.revision, permissions});
            if (!data.result?.saved || !/^[a-f0-9]{64}$/.test(data.result.revision || '')) {
              state.textContent = '保存结果无法确认，请重新搜索'; return;
            }
            item.revision = data.result.revision;
            state.textContent = '保存成功';
            checkboxes.forEach(el => { el.disabled = false; }); save.disabled = false;
          } catch (error) {
            state.textContent = `保存失败：${error.message}。如请求超时，请重新搜索确认结果。`;
            checkboxes.forEach(el => { el.disabled = false; }); save.disabled = false;
          }
        };
        actions.append(save);
      }
      row.append(actions); body.append(row);
    }
    table.append(body); wrapper.append(table); results.append(wrapper);
  }
  let searching = false;
  form.onsubmit = async event => {
    event.preventDefault(); if (searching) return;
    const username = input.value.trim(); if (!username) return;
    searching = true; form.querySelector('button').disabled = true; results.replaceChildren(); message.textContent = '正在查询...';
    try {
      const data = await request('/api/jenkins/permissions/search', {username});
      message.textContent = data.results.length ? `用户 ${username} 的查询结果` : '暂无 Jenkins';
      if (data.results.length) renderMatrix(data.results, username);
    } catch (error) { message.textContent = `查询失败：${error.message}`; }
    finally { searching = false; form.querySelector('button').disabled = false; }
  };
}
