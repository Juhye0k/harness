"use strict";
const $ = id => document.getElementById(id);
const params = new URL(location.href).searchParams;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
let data, revision, currentJob, timer, epoch = 0, busy = false, dirty = false;
const base = `/analyses/${params.get('analysis')}/candidates/${params.get('candidate')}`;
const pendingCaptionKey='shortform.pending-caption:'+base;
function pendingCaption(){try{return JSON.parse(sessionStorage.getItem(pendingCaptionKey)||'null');}catch{return null;}}
const make = (tag, text) => {const n=document.createElement(tag); n.textContent=text; return n;};
async function api(path, body) {
  const response=await fetch(path, {method:body===undefined?'GET':'POST', cache:'no-store',
    headers:body===undefined?{}:{'Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)}), signal:AbortSignal.timeout(15000)});
  const result=await response.json();
  if(!response.ok){const error=new Error(result.error?.message || `요청 오류 (${response.status})`);error.status=response.status;throw error;}
  return result;
}
function query(key, value) {
  const url=new URL(location.href);
  if(value)url.searchParams.set(key,value);else url.searchParams.delete(key);
  history.replaceState(null,'',url);
}
function invalidate() {
  if(busy)return;
  dirty=true; epoch++; clearTimeout(timer); currentJob=null;
  $('caption-reviewed').checked=false;
  $('render-final').disabled=true; $('final-result').hidden=true; $('retry-render').hidden=true;
  $('final-preview').pause(); $('render-state').textContent='변경한 편집본을 저장한 뒤 출력하세요.';
  $('draft-status').textContent='저장하지 않은 변경이 있습니다.';
  query('job',null);
}
function addRow(cue) {
  const row=document.createElement('div'); row.className='caption-row';
  const selector=document.createElement('select'); selector.className='cue-segment';
  for(const segment of data.segments){
    const option=make('option',`${segment.id} · ${segment.text}`);option.value=segment.id;selector.append(option);
  }
  selector.value=cue.source_segment_id || data.segments[0].id;
  const segmentLabel=make('label','원 구간');segmentLabel.append(selector);row.append(segmentLabel);
  for(const [key,label] of [['start_ms','시작 (초)'],['end_ms','종료 (초)']]) {
    const input=document.createElement('input');input.type='number';input.step='0.001';input.min='0';
    input.max=String((data.end_ms-data.start_ms)/1000);input.className=key;
    input.value=cue[key]===undefined?'':((cue[key]-data.start_ms)/1000).toFixed(3);
    const wrapper=make('label',label);wrapper.append(input);row.append(wrapper);
  }
  const text=document.createElement('textarea');text.className='cue-text';text.value=(cue.lines||[]).join('\n');
  const wrapper=make('label','자막 (최대 2줄)');wrapper.className='cue-text-label';wrapper.append(text);row.append(wrapper);
  const remove=make('button','삭제');remove.type='button';remove.className='secondary';
  remove.onclick=()=>{if(!busy){row.remove();invalidate();}};row.append(remove);
  row.addEventListener('input',invalidate);$('caption-rows').append(row);
}
function cues() {
  return [...document.querySelectorAll('.caption-row')].map(row=>{
    const time=key=>{const raw=row.querySelector('.'+key).value;if(!raw.trim())throw new Error('자막 시작·종료 시간을 입력하세요.');return Math.round(Number(raw)*1000)+data.start_ms;};
    return {source_segment_id:row.querySelector('.cue-segment').value,start_ms:time('start_ms'),end_ms:time('end_ms'),lines:row.querySelector('.cue-text').value.split('\n')};
  });
}
function showRevision(saved) {
  revision=saved;dirty=false;
  $('caption-rows').replaceChildren();for(const cue of saved.cues)addRow(cue);
  $('caption-reviewed').checked=saved.reviewed;
  $('final-panel').hidden=false;$('render-final').disabled=!saved.reviewed;
  $('draft-status').textContent='저장한 편집본입니다. 원본 전사는 변경하지 않았습니다.';
  $('revision-status').textContent=`편집 버전: ${saved.revision_id} · ${saved.reviewed?'원음 확인 완료':'원음 확인 전'}`;
  query('revision',saved.revision_id);
}
async function pollJob(id, version=epoch) {
  clearTimeout(timer);$('retry-render').hidden=true;
  try {
    const job=await api(`/jobs/${id}`);
    if(version!==epoch || dirty)return;
    if(job.status==='succeeded'){
      if(job.result?.render?.revision_id!==revision.revision_id)throw new Error('편집 버전과 출력이 다릅니다.');
      $('render-state').textContent='완성 영상을 확인하고 다운로드하거나 YouTube 업로드로 이동하세요.';
      $('final-result').hidden=false;
      const src=job.download_url;
      if($('final-preview').getAttribute('src')!==src)$('final-preview').src=src;
      $('final-download').href=src;$('final-srt').href=`/jobs/${id}/subtitles.srt`;$('final-sns').href=`/sns?job=${id}`;
      $('render-final').disabled=true;
    }else if(job.status==='failed'){
      $('render-state').textContent=`출력 실패: ${job.error?.message || job.error?.code}. 자동 재실행하지 않습니다.`;
      $('render-final').disabled=true;
    }else{
      $('render-state').textContent=job.status==='running'?'자막을 입혀 세로 영상으로 만드는 중입니다.':'영상 출력 대기 중입니다.';
      $('render-final').disabled=true;timer=setTimeout(()=>pollJob(id,version),1500);
    }
  }catch(error){if(version===epoch){$('render-state').textContent=`출력 상태 조회 오류: ${error.message} 처리 실패를 의미하지 않습니다.`;$('retry-render').hidden=false;}}
}
function lock(value){busy=value;$('editor-panel').querySelectorAll('input,textarea,select,button').forEach(n=>n.disabled=value);}
async function start(){
  $('retry-editor').hidden=true;
  if(!uuid.test(params.get('analysis')||'') || !uuid.test(params.get('candidate')||'')){$('editor-message').textContent='추천 결과에서 편집할 구간을 선택하세요.';return;}
  try{
    data=await api(base+'/editor');
    $('back').href=`/recommendations?analysis=${data.analysis_id}`;
    $('candidate-title').textContent=`${data.title} · ${data.start_ms/1000}~${data.end_ms/1000}초`;
    $('editor-panel').hidden=false;$('final-panel').hidden=false;
    const video=$('source-preview');video.src=`/analyses/${data.analysis_id}/source-video`;
    video.onloadedmetadata=()=>{video.currentTime=data.start_ms/1000;};
    video.ontimeupdate=()=>{
      if(video.currentTime>=data.end_ms/1000)video.pause();
      try{const cue=cues().find(c=>c.start_ms<=video.currentTime*1000&&c.end_ms>video.currentTime*1000);$('caption-preview').textContent=cue?cue.lines.join('\n'):'';}catch{$('caption-preview').textContent='';}
    };
    video.onerror=()=>{$('editor-message').textContent='원본 영상 재생을 확인하지 못했습니다. 저장 상태와는 별개입니다.';};
    $('editor-transcript').replaceChildren(...data.segments.map(s=>make('p',`${s.id} · ${s.text}`)));
    const requested=params.get('revision');
    if(requested && !uuid.test(requested))throw new Error('편집 버전 번호를 확인하세요.');
    const pending=pendingCaption();
    const canonical=items=>JSON.stringify(items.map(c=>[c.source_segment_id,c.start_ms,c.end_ms,c.lines]));
    const matches=(candidate)=>candidate&&candidate.source_version===pending?.source_version&&candidate.reviewed===pending.reviewed&&canonical(candidate.cues)===canonical(pending.cues);
    let saved;
    if(pending){
      if(matches(data.latest_revision)){saved=data.latest_revision;sessionStorage.removeItem(pendingCaptionKey);}
      else{
        revision=null;dirty=true;$('render-final').disabled=true;$('final-result').hidden=true;
        $('caption-rows').replaceChildren();for(const cue of pending.cues)addRow(cue);
        $('caption-reviewed').checked=pending.reviewed;
        $('draft-status').textContent='저장 응답을 확인하지 못한 편집 내용입니다. 같은 내용을 다시 저장하면 기존 버전을 재사용합니다.';
        $('editor-message').textContent='저장 결과 미확정: 원본과 내용을 확인한 뒤 같은 편집본을 저장하세요.';
        return;
      }
    }else saved=requested?await api(base+'/caption-revisions/'+requested):data.latest_revision;
    if(saved){
      showRevision(saved);
      // Persisted version owns its output; never accept an arbitrary job from the URL.
      if(saved.render_job_id){currentJob=saved.render_job_id;query('job',currentJob);await pollJob(currentJob);}
    }else{
      $('caption-rows').replaceChildren();
      const initial=[...data.suggested.cues];
      for(const blocked of data.suggested.blocked_segments)initial.push({source_segment_id:blocked.id,start_ms:Math.max(blocked.start_ms,data.start_ms),end_ms:Math.min(blocked.end_ms,data.end_ms),lines:[blocked.text]});
      initial.sort((a,b)=>a.start_ms-b.start_ms);for(const cue of initial)addRow(cue);
      $('draft-status').textContent=data.suggested.quality_pass?'자동 자막 초안입니다. 원음을 확인한 뒤 저장하세요.':'자동 분할이 부족한 구간이 있습니다. 긴 문구·시간을 나누고 원음을 확인하세요.';
    }
    $('editor-message').textContent='선택한 후보의 자막을 편집할 수 있습니다.';
  }catch(error){$('editor-message').textContent=error.message;$('retry-editor').hidden=false;}
}
$('play-clip').onclick=()=>{const video=$('source-preview');video.currentTime=data.start_ms/1000;video.play().catch(()=>{$('editor-message').textContent='원본 영상을 재생하지 못했습니다.';});};
$('add-cue').onclick=()=>{if(!busy){addRow({});invalidate();}};
$('caption-reviewed').onchange=()=>{dirty=true;epoch++;clearTimeout(timer);currentJob=null;$('render-final').disabled=true;$('final-result').hidden=true;$('retry-render').hidden=true;$('final-preview').pause();query('job',null);$('draft-status').textContent='확인 상태를 저장해 주세요.';$('render-state').textContent='변경한 확인 상태를 저장한 뒤 출력하세요.';};
$('save-captions').onclick=async()=>{
  if(busy)return;lock(true);$('editor-message').textContent='';
  try{
    const body={source_version:data.source_version,cues:cues(),reviewed:$('caption-reviewed').checked};
    sessionStorage.setItem(pendingCaptionKey,JSON.stringify(body));
    const saved=await api(base+'/caption-revisions',body);
    sessionStorage.removeItem(pendingCaptionKey);
    epoch++;clearTimeout(timer);$('final-result').hidden=true;currentJob=null;query('job',null);showRevision(saved);
    $('editor-message').textContent='편집본을 저장했습니다.';
    if(saved.render_job_id){currentJob=saved.render_job_id;query('job',currentJob);await pollJob(currentJob);}
  }catch(error){if(error.status===422)sessionStorage.removeItem(pendingCaptionKey);$('editor-message').textContent=`저장 결과를 확인하지 못했습니다. ${error.message} 저장됐을 수 있으니 화면을 다시 조회하거나 같은 편집본을 저장하세요.`;$('retry-editor').hidden=false;}
  finally{lock(false);}
};
$('render-final').onclick=async()=>{
  if(busy || dirty || !revision?.reviewed)return;lock(true);$('render-final').disabled=true;
  try{
    const job=await api(`${base}/caption-revisions/${revision.revision_id}/exports`,{});
    currentJob=job.job_id;query('job',currentJob);await pollJob(currentJob);
  }catch(error){$('render-state').textContent=`접수 결과를 확인하지 못했습니다. ${error.message} 같은 편집본으로 다시 조회하세요.`;$('render-final').disabled=false;}
  finally{lock(false);}
};
$('retry-editor').onclick=start;$('retry-render').onclick=()=>currentJob&&pollJob(currentJob);
start();
