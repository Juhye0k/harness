"use strict";
let offset = 0;
const notice = document.getElementById('notice');
async function api(path, method='GET') {
  const r = await fetch(path, {method, cache:'no-store'});
  const data = await r.json();
  if (!r.ok) throw new Error(data.error?.message || '요청을 완료하지 못했습니다.');
  return data;
}
async function load() {
  try {
    const area = document.getElementById('data'); area.replaceChildren();
    for (const type of ['assets', 'jobs']) {
      const rows = await api(`/${type}?offset=${offset}`);
      for (const row of rows) {
        const article = document.createElement('article');
        const label = document.createElement('p'); label.textContent = `${type === 'assets' ? '원본' : '출력'} ${row.id} · ${row.status} · 만료 ${new Date(row.expires_at).toLocaleString()}${row.deleting ? ' · 삭제 중' : ''}`;
        const button = document.createElement('button'); button.textContent='삭제 범위 확인'; button.disabled=row.deleting;
        button.onclick = async () => {
          try {
            const preview = await api(`/${type}/${row.id}/deletion-preview`);
            if (!confirm(`출력 ${preview.outputs.length}개${preview.includes_original ? '와 원본·전사·분석·검수·검증 자료' : ''}를 삭제합니다. 계속할까요?`)) return;
            const deletion = await api(`/${type}/${row.id}`, 'DELETE');
            poll(deletion.status_url); await load();
          } catch(e) { notice.textContent=e.message; }
        };
        article.append(label, button); area.append(article);
      }
    }
  } catch(e) { notice.textContent=e.message; }
}
async function poll(url, token) {
  try {
    const r = token ? await window.fetchNativeDeletion(url, token) : await fetch(url);
    const state = await r.json();
    notice.textContent=`삭제 상태: ${state.state}${state.error ? ' · '+state.error : ''}`;
    if (!['complete','failed'].includes(state.state)) setTimeout(() => poll(url, token), 3000);
  } catch(e) { notice.textContent=e.message; }
}
window.fetchNativeDeletion = (url, token) => fetch(url, {headers:{'X-Deletion-Token':token}});
document.getElementById('more').onclick=() => { offset+=50; load(); };
document.getElementById('leave').onclick=async () => {
  if (!confirm('계정 접근이 즉시 차단되고 모든 앱 자료가 정리됩니다. YouTube 게시물은 유지됩니다. 탈퇴할까요?')) return;
  try {
    const result=await api('/auth/me','DELETE');
    localStorage.clear(); sessionStorage.clear();
    poll(result.status_url,result.token);
  } catch(e) { notice.textContent=e.message; }
};
load();
