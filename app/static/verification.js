"use strict";
const byId=id=>document.getElementById(id);
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
let epoch=0;
async function load(){
 const current=++epoch,id=new URL(location.href).searchParams.get('analysis');
 if(!id)return;
 byId('analysis').value=id;
 if(!/^[0-9a-f-]{36}$/i.test(id)){byId('message').textContent='分析番号が不正'.replace('分析番号が不正','분석 번호를 확인하세요.');return;}
 byId('download').hidden=true; byId('cues').replaceChildren(); byId('blocked').replaceChildren(); byId('states').replaceChildren(); byId('summary').textContent='';
 try{
  const r=await fetch(`/analyses/${id}/verification`);if(!r.ok)throw new Error('검증 정보 조회 실패');
  const data=await r.json();if(current!==epoch)return;
  byId('message').textContent='저장된 분석을 조회했습니다. 새 작업이나 AI 호출을 만들지 않습니다.';
  const labels={passed:'통과',unknown:'미확인',stale:'이전 코드의 결과',incomplete:'일부 검사 미실행'};
  byId('states').replaceChildren(node('p',`처리: ${data.processing}`),node('p',`코드 검사: ${labels[data.code.status]||data.code.status}`),
   node('p',`표시 품질: ${data.display?.quality_pass?'통과':'검수 필요'}`),
   node('p',`전사 사람 검토: ${data.transcript_human_review.status==='complete'?'완료':'미완료'}`));
  if(!data.display)return;
  const d=data.display;
  const audio=byId('preview-audio');audio.src=`/analyses/${id}/review-audio`;
  audio.ontimeupdate=()=>{const cue=d.cues.find(c=>c.start_ms<=audio.currentTime*1000&&c.end_ms>audio.currentTime*1000);byId('active-caption').textContent=cue?cue.lines.join('\n'):'';};
  byId('summary').textContent=`기존 ${data.baseline.cues}개 → 생성 가능 ${d.cues.length}개 · 검수 필요 원 구간 ${d.blocked_segments.length}/${d.source_segments}개 · 전체 커버리지 ${d.coverage_complete?'완료':'미완료'}`;
  byId('cues').replaceChildren(...d.cues.map(c=>node('p',`${c.start_ms/1000}~${c.end_ms/1000}초 · ${c.lines.join(' / ')}`)));
  byId('blocked').replaceChildren(...d.blocked_segments.map(s=>node('p',`${s.start_ms/1000}~${s.end_ms/1000}초 · ${s.reason} · ${s.text}`)));
  byId('review').href=`/recommendations?analysis=${id}`;
  const assets=byId('assets');assets.replaceChildren();
  for(const file of ['before.png','after.png','remaining-long.png']){const img=document.createElement('img');img.alt=file;img.style.maxWidth='100%';img.src=`/analyses/${id}/verification/assets/${file}`;img.onerror=()=>img.remove();assets.append(img);}
  const video=document.createElement('video');video.controls=true;video.preload='none';video.style.maxWidth='100%';video.src=`/analyses/${id}/verification/assets/preview-after.mp4`;video.onerror=()=>video.remove();assets.append(video);
  byId('download').href=`/analyses/${id}/subtitles.srt?profile=shorts-display-v1`;
  byId('download').hidden=!d.quality_pass;
 }catch(error){if(current===epoch)byId('message').textContent=error.message+' · 처리 실패를 의미하지 않습니다.';}
}
byId('lookup').onsubmit=e=>{e.preventDefault();history.pushState({},'',`/verification?analysis=${encodeURIComponent(byId('analysis').value)}`);load();};
const fullscreen=byId('fullscreen');
fullscreen.hidden=!document.fullscreenEnabled;
fullscreen.onclick=async()=>{
 try{
  if(document.fullscreenElement)await document.exitFullscreen();
  else await document.documentElement.requestFullscreen();
 }catch{
  byId('message').textContent='이 브라우저에서 전체 화면을 열 수 없습니다. 브라우저의 전체 화면 기능을 사용해 주세요.';
 }
};
document.addEventListener('fullscreenchange',()=>{
 const active=Boolean(document.fullscreenElement);
 fullscreen.textContent=active?'전체 화면 종료':'전체 화면';
 fullscreen.setAttribute('aria-pressed',String(active));
});
window.addEventListener('popstate',load);load();
