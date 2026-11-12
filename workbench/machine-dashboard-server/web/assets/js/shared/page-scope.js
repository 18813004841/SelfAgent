// 页面卸载时取消请求、定时器；取消后的异步流程停在页面边界。
export function createPageScope() {
  const controller = new AbortController();
  const timers = new Set();
  let disposed = false;
  const cancelled = () => new Promise(() => {});
  return {
    async fetch(url, options = {}) {
      if (disposed) return cancelled();
      try {
        const response = await window.fetch(url, {
          ...options,
          signal: controller.signal,
        });
        if (disposed) return cancelled();
        return response;
      } catch (error) {
        if (controller.signal.aborted) return cancelled();
        throw error;
      }
    },
    setInterval(callback, delay) {
      if (disposed) return undefined;
      const timer = window.setInterval(() => {
        if (!disposed) callback();
      }, delay);
      timers.add(timer);
      return timer;
    },
    dispose() {
      disposed = true;
      controller.abort();
      for (const timer of timers) window.clearInterval(timer);
      timers.clear();
    },
  };
}
