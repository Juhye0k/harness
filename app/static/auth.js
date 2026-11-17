"use strict";
(() => {
  const original = window.fetch.bind(window);
  let identity, userActivity = false;
  for (const name of ['click', 'keydown', 'play']) document.addEventListener(name, event => {
    if (event.isTrusted) userActivity = true;
  }, true);
  async function session() {
    if (!identity) identity = original('/auth/me', {cache:'no-store'}).then(async r => {
      if (r.status === 401) return {required:true};
      if (!r.ok) throw new Error('로그인 상태를 확인하지 못했습니다.');
      const data = await r.json();
      if (data.enabled) {
        const previous = localStorage.getItem('shortform-user');
        if (previous !== data.user_id) {
          localStorage.clear();
          sessionStorage.clear();
          localStorage.setItem('shortform-user', data.user_id);
        }
      }
      return data;
    }).catch(e => { identity = null; throw e; });
    return identity;
  }
  window.fetch = async (input, init = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin !== location.origin || url.pathname.startsWith('/auth/google/') || url.pathname.startsWith('/deletion-status/')) return original(input, init);
    const auth = await session();
    if (auth.required) { location.assign('/login'); throw new Error('로그인이 필요합니다.'); }
    const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
    if (auth.enabled) headers.set('X-CSRF-Token', auth.csrf);
    if (userActivity) { headers.set('X-User-Activity', '1'); userActivity = false; }
    const response = await original(input, {...init, headers});
    if (response.status === 401) { identity = null; location.assign('/login'); }
    return response;
  };
  document.addEventListener('DOMContentLoaded', async () => {
    if (location.pathname === '/login') return;
    try {
      const auth = await session();
      if (auth.required) { location.assign('/login'); return; }
      if (auth.enabled) {
        const nav = document.createElement('nav');
        const link = document.createElement('a'); link.href='/my-data'; link.textContent='내 자료 · 보관/삭제';
        const logout = document.createElement('button'); logout.textContent='로그아웃';
        logout.onclick = async () => { await window.fetch('/auth/logout', {method:'POST'}); localStorage.clear(); sessionStorage.clear(); location.assign('/login'); };
        nav.append(link, logout); document.body.prepend(nav);
      }
    } catch (_) { /* Existing screen reports request failures. */ }
  });
})();
