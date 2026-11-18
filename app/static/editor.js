"use strict";
const $ = id => document.getElementById(id);
const params = new URL(location.href).searchParams;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
let data, revision, currentJob, currentJobProfile, timer, epoch = 0, busy = false, dirty = false;
const base = `/analyses/${params.get('analysis')}/candidates/${params.get('candidate')}`;
const pendingCaptionKey='shortform.pending-caption:'+base;
function pendingCaption(){try{return JSON.parse(sessionStorage.getItem(pendingCaptionKey)||'null');}catch{return null;}}
const make = (tag, text) => {const n=document.createElement(tag); n.textContent=text; return n;};
async function api(path, body) {
  const response=await fetch(path, {method:body===undefined?'GET':'POST', cache:'no-store',
    headers:body===undefined?{}:{'Content-Type':'application/json'},
    ...(body===undefined?{}:{body:JSON.stringify(body)}), signal:AbortSignal.timeout(15000)});
  const result=await response.json();
  if(!response.ok){const error=new Error(result.error?.message || `요청 오류 (${response.status})`);error.status=response.status;error.code=result.error?.code;throw error;}
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
function showComparison(revisionId) {
  const compare=$('compare-revision');
  const viewingLatest=data.latest_revision?.revision_id===revisionId;
  const otherId=viewingLatest?data.previous_revision_id:data.latest_revision?.revision_id;
  compare.hidden=!otherId;
  if(otherId){
    const url=new URL(location.href);url.searchParams.set('revision',otherId);url.searchParams.delete('job');
    compare.href=url;
    compare.textContent=viewingLatest?'직전 저장본을 새 탭에서 열기':'최신 저장본을 새 탭에서 열기';
  }
}
function showRevision(saved) {
  revision=saved;dirty=false;
  $('caption-rows').replaceChildren();for(const cue of saved.cues)addRow(cue);
  $('caption-reviewed').checked=saved.reviewed;
  $('final-panel').hidden=false;$('render-final').disabled=!saved.reviewed;
  $('draft-status').textContent='저장한 편집본입니다. 원본 전사는 변경하지 않았습니다.';
  $('revision-status').textContent=`편집 버전: ${saved.revision_id} · ${saved.reviewed?'원음 확인 완료':'원음 확인 전'}`;
  showComparison(saved.revision_id);
  query('revision',saved.revision_id);
}
function draftStatus() {
  if(data.alignment?.status==='aligned'){
    const cut=data.alignment.cut_words;
    return '화면 전환과 전사 단어 시각으로 나눈 초안입니다. '
      +(cut?`후보 경계에 걸친 단어 ${cut}개를 확인하세요. `:'')+'미확정 상태로 저장할 수 있습니다.';
  }
  if(!data.suggested.quality_pass)return '직접 검토할 구간이 있습니다. 긴 문구와 시간을 나누고 원음을 확인하세요.';
  return data.alignment?.status==='alignment_needs_review'
    ?'화면 정렬에 필요한 조건을 충족하지 않아 전사 시각으로 만든 초안입니다. 원음을 확인하세요.'
    :'저장한 전사 시각으로 만든 초안입니다. 원음을 확인하세요.';
}
function isPreviousProfile() {
  return Boolean(currentJobProfile && data.export_profile && currentJobProfile!==data.export_profile);
}
async function pollJob(id, version=epoch) {
  clearTimeout(timer);$('retry-render').hidden=true;
  try {
    const job=await api(`/jobs/${id}`);
    if(version!==epoch || dirty)return;
    const previousProfile=isPreviousProfile();
    $('render-final').disabled=!previousProfile || !revision.reviewed;
    if(job.status==='succeeded'){
      if(job.result?.render?.revision_id!==revision.revision_id)throw new Error('편집 버전과 출력이 다릅니다.');
      if(currentJobProfile && job.result.render.profile!==currentJobProfile)throw new Error('저장한 출력 설정과 영상이 다릅니다.');
      $('render-state').textContent=previousProfile
        ?'이전 화면 구성의 출력입니다. 다운로드하거나 새 화면 구성으로 다시 만들 수 있습니다.'
        :'완성 영상을 확인하고 다운로드하거나 YouTube 업로드로 이동하세요.';
      $('final-result').hidden=false;
      const src=job.download_url;
      if($('final-preview').getAttribute('src')!==src)$('final-preview').src=src;
      $('final-download').href=src;$('final-srt').href=`/jobs/${id}/subtitles.srt`;$('final-sns').href=`/sns?job=${id}`;
    }else if(job.status==='failed'){
      $('render-state').textContent=`출력 실패: ${job.error?.message || job.error?.code}. 자동 재실행하지 않습니다.`;
    }else{
      $('render-state').textContent=job.status==='running'?'자막을 입혀 세로 영상으로 만드는 중입니다.':'영상 출력 대기 중입니다.';
      timer=setTimeout(()=>pollJob(id,version),1500);
    }
  }catch(error){if(version===epoch){$('render-state').textContent=`출력 상태 조회 오류: ${error.message} 처리 실패를 의미하지 않습니다.`;$('retry-render').hidden=false;}}
}
async function openJob(id, profile) {
  currentJob=id;
  currentJobProfile=profile;
  $('render-final').disabled=!isPreviousProfile() || !revision.reviewed;
  query('job',id);
  await pollJob(id);
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
    const requested=new URL(location.href).searchParams.get('revision');
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
        showComparison(null);
        $('draft-status').textContent='저장 응답을 확인하지 못한 편집 내용입니다. 같은 내용을 다시 저장하면 기존 버전을 재사용합니다.';
        $('editor-message').textContent='저장 결과 미확정: 원본과 내용을 확인한 뒤 같은 편집본을 저장하세요.';
        return;
      }
    }else saved=requested?await api(base+'/caption-revisions/'+requested):data.latest_revision;
    if(saved){
      showRevision(saved);
      // Persisted version owns its output; never accept an arbitrary job from the URL.
      if(saved.render_job_id)await openJob(saved.render_job_id,saved.render_profile);
    }else{
      $('caption-rows').replaceChildren();
      const initial=[...data.suggested.cues];
      for(const blocked of data.suggested.blocked_segments)initial.push({source_segment_id:blocked.id,start_ms:Math.max(blocked.start_ms,data.start_ms),end_ms:Math.min(blocked.end_ms,data.end_ms),lines:[blocked.text]});
      initial.sort((a,b)=>a.start_ms-b.start_ms);for(const cue of initial)addRow(cue);
      $('draft-status').textContent=draftStatus();
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
    const body={source_version:data.source_version,cues:cues(),reviewed:$('caption-reviewed').checked,
      expected_latest_revision_id:data.latest_revision?.revision_id||null};
    sessionStorage.setItem(pendingCaptionKey,JSON.stringify(body));
    const saved=await api(base+'/caption-revisions',body);
    sessionStorage.removeItem(pendingCaptionKey);
    if(!data.latest_revision || new Date(saved.created_at)>new Date(data.latest_revision.created_at)){
      data.previous_revision_id=data.latest_revision?.revision_id;
      data.latest_revision=saved;
    }
    epoch++;clearTimeout(timer);$('final-result').hidden=true;currentJob=null;query('job',null);showRevision(saved);
    $('editor-message').textContent='편집본을 저장했습니다.';
    if(saved.render_job_id)await openJob(saved.render_job_id,saved.render_profile);
  }catch(error){
    if(error.status===422)sessionStorage.removeItem(pendingCaptionKey);
    $('editor-message').textContent=error.code==='REVISION_CONFLICT'
      ?'다른 편집본이 저장됐습니다. 최신 버전과 현재 입력을 비교한 뒤 저장하세요.'
      :`저장 결과를 확인하지 못했습니다. ${error.message} 화면을 다시 조회하거나 같은 내용을 저장하세요.`;
    $('retry-editor').hidden=false;
  }
  finally{lock(false);}
};
$('render-final').onclick=async()=>{
  if(busy || dirty || !revision?.reviewed)return;lock(true);$('render-final').disabled=true;
  epoch++;clearTimeout(timer);
  try{
    const job=await api(`${base}/caption-revisions/${revision.revision_id}/exports`,{});
    $('final-result').hidden=true;$('final-preview').pause();
    await openJob(job.job_id,job.render_profile);
  }catch(error){$('render-state').textContent=`접수 결과를 확인하지 못했습니다. ${error.message} 같은 편집본으로 다시 조회하세요.`;$('render-final').disabled=false;}
  finally{lock(false);}
};
$('retry-editor').onclick=start;$('retry-render').onclick=()=>currentJob&&pollJob(currentJob);
start();
