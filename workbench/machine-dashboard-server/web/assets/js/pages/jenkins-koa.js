const form = document.querySelector('#koa-form');
const button = document.querySelector('#koa-submit');
const status = document.querySelector('#koa-status');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  button.disabled = true;
  status.textContent = '查询中…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch('/api/jenkins/last-completed', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ip: document.querySelector('#koa-ip').value.trim(), job: document.querySelector('#koa-job').value.trim()}),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || `HTTP ${response.status}`);
    status.textContent = `最后完成构建 #${data.build.number} · ${data.build.result}`;
  } catch (error) {
    status.textContent = error.name === 'AbortError' ? '查询超时，请重试。' : `查询失败：${error.message}`;
  } finally {
    clearTimeout(timer);
    button.disabled = false;
  }
});
