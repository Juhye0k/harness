"use strict";
const el = (id) => document.getElementById(id);
let generation = 0, timer, currentId;
let selection = 0, chosen, candidates = [], showingOutput = false;
let submitting = false;
const pendingKey = "shortform.pending-analysis";
function pendingAnalysis(){try{return JSON.parse(sessionStorage.getItem(pendingKey)||"null");}catch{return null;}}
function requestId(){
  const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
  const hex=Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
function pendingControls(){
  const pending=Boolean(pendingAnalysis());
  el("analyze").disabled=submitting||pending||(el("url").disabled&&!window.uploadedAssetId);
  el("recover-analysis").hidden=!pending;el("resubmit-analysis").hidden=!pending;
  el("recover-analysis").disabled=submitting;el("resubmit-analysis").disabled=submitting;
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
async function request(url, body) {
  const response = await fetch(url, {method: body ? "POST" : "GET", cache:"no-store",
    headers: body ? {"Content-Type": "application/json"} : {},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(15000)});
  const data = await response.json();
  if (!response.ok) {const error=new Error(data.error?.message || `조회 오류 (${response.status})`);error.status=response.status;throw error;}
  return data;
}
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function time(ms) {
  const seconds = Math.floor(ms / 1000);
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}
function editUrl(id) {
  return "/editor?" + new URLSearchParams({analysis:currentId, candidate:id});
}
function render(data) {
  candidates = data.candidates;
  el("candidate-workspace").hidden = !candidates.length;
  el("candidate-count").textContent = candidates.length + "개";
  el("candidates").replaceChildren(...candidates.map(item => {
    const article = document.createElement("article");
    article.className = "candidate";
    const select = node("button", `${item.rank}. ${item.title}`);
    select.type = "button";
    select.className = "candidate-select";
    select.dataset.id = item.id;
    select.onclick = () => {
      if (chosen?.id === item.id) return;
      const url = new URL(location.href);
      url.searchParams.set("candidate", item.id);
      history.replaceState(null, "", url);
      selectCandidate(item);
    };
    const title = document.createElement("h3");
    title.append(select);
    const edit = node("a", "자막 편집 →");
    edit.className = "edit-candidate";
    edit.href = editUrl(item.id);
    article.append(title, node("p", `${time(item.start_ms)}–${time(item.end_ms)} · 편집 적합도 ${item.score}/100`), edit);
    return article;
  }));
  if (candidates.length) {
    const id = new URLSearchParams(location.search).get("candidate");
    selectCandidate(candidates.find(item => item.id === id) || candidates[0]);
  }
}
async function selectCandidate(item) {
  const version = ++selection;
  chosen = item;
  showingOutput = false;
  const analysis = currentId;
  const editor = editUrl(item.id);
  const base = `/analyses/${analysis}/candidates/${item.id}`;
  const video = el("clip-preview");
  video.pause();
  const source = `/analyses/${analysis}/source-video`;
  if (video.getAttribute("src") !== source) video.src = source;
  else if (video.readyState >= 1) video.currentTime = item.start_ms / 1000;
  el("play-candidate").hidden = false;
  el("clip-title").textContent = item.title;
  el("clip-timing").textContent = `원본 ${time(item.start_ms)}–${time(item.end_ms)} · ${((item.end_ms-item.start_ms)/1000).toFixed(1)}초`;
  el("clip-state").textContent = "원본 구간 미리보기";
  el("clip-edit").href = editor;
  el("clip-reason").textContent = item.reason;
  const labels = {hook:"도입", completeness:"완결성", context_independence:"독립성", memorable:"인상", editability:"편집성"};
  el("clip-scores").textContent = Object.entries(item.scores).map(([key,value]) => `${labels[key]} ${value}/4`).join(" · ");
  el("clip-transcript").textContent = item.segments.map(segment => segment.text).join(" ");
  for (const button of el("candidates").querySelectorAll(".candidate-select")) {
    button.setAttribute("aria-pressed", String(button.dataset.id === item.id));
  }
  for (const id of ["clip-download", "clip-srt", "clip-sns"]) {
    el(id).hidden = true;
    el(id).removeAttribute("href");
  }
  const extract = el("clip-extract");
  extract.replaceChildren();
  if (item.export_job_id) {
    const link = node("a", "추출 상태 · 미리보기 · 다운로드 →");
    link.href = "/extract?job=" + encodeURIComponent(item.export_job_id);
    extract.append(link);
  } else {
    const button = node("button", "이 구간 추출하기");
    button.type = "button";
    button.className = "secondary studio-fit";
    button.onclick = async () => {
      button.disabled = true;
      try {
        const result = await request(base + "/exports", {});
        if (version === selection) location.assign("/extract?job=" + encodeURIComponent(result.job_id));
      } catch (error) {
        if (version !== selection) return;
        el("clip-state").textContent = error.message + " 기존 추출 작업을 다시 조회하세요.";
        el("refresh").hidden = false;
      }
    };
    extract.append(button);
  }
  try {
    const {latest_revision: saved} = await request(base + "/editor");
    if (version !== selection || !saved) return;
    if (!saved.render_job_id) {
      el("clip-state").textContent = saved.reviewed ? "원음 확인 완료 · 편집기에서 출력을 시작하세요." : "미검수 편집본 저장됨";
      return;
    }
    const job = await request("/jobs/" + encodeURIComponent(saved.render_job_id));
    if (version !== selection) return;
    if (job.status !== "succeeded") {
      el("clip-state").textContent = job.status === "failed" ? "출력 실패 · 편집기에서 확인하세요." : "출력 중 · 편집기에서 진행 상태를 확인할 수 있습니다.";
      return;
    }
    if (!saved.reviewed || job.result?.render?.revision_id !== saved.revision_id) throw new Error("Output mismatch");
    const jobPath = "/jobs/" + encodeURIComponent(saved.render_job_id);
    showingOutput = true;
    video.src = jobPath + "/download";
    el("play-candidate").hidden = true;
    el("clip-state").textContent = "완성 영상 · 다운로드하거나 YouTube에 게시할 수 있습니다.";
    el("clip-download").href = jobPath + "/download";
    el("clip-srt").href = jobPath + "/subtitles.srt";
    el("clip-sns").href = "/sns?" + new URLSearchParams({job:saved.render_job_id, analysis, candidate:item.id, revision:saved.revision_id});
    for (const id of ["clip-download", "clip-srt", "clip-sns"]) el(id).hidden = false;
  } catch {
    if (version !== selection) return;
    el("clip-state").textContent = "편집·출력 상태를 조회하지 못했습니다. 편집기에서 다시 확인할 수 있습니다.";
  }
}
const preview = el("clip-preview");
preview.onloadedmetadata = () => {
  if (chosen && !showingOutput) preview.currentTime = chosen.start_ms / 1000;
};
preview.ontimeupdate = () => {
  if (!chosen || showingOutput || preview.paused) return;
  if (preview.currentTime < chosen.start_ms / 1000 - 0.03) preview.currentTime = chosen.start_ms / 1000;
  if (preview.currentTime >= chosen.end_ms / 1000) preview.pause();
};
preview.onplay = () => {
  if (chosen && !showingOutput && (preview.currentTime < chosen.start_ms / 1000 || preview.currentTime >= chosen.end_ms / 1000)) {
    preview.currentTime = chosen.start_ms / 1000;
  }
};
el("play-candidate").onclick = () => {
  if (!chosen) return;
  if (preview.readyState >= 1) preview.currentTime = chosen.start_ms / 1000;
  preview.play().catch(() => { el("clip-state").textContent = "원본을 재생하지 못했습니다."; });
};
async function renderTranscript(id, epoch, showVerification = true) {
  try {
    const [transcript, subtitles] = await Promise.all([
      request(`/analyses/${id}/transcript`), request(`/analyses/${id}/subtitles?profile=shorts-display-v1`)
    ]);
    if (epoch !== generation) return;
    el("segments").replaceChildren(); el("subtitle-cues").replaceChildren();
    for (const s of transcript.segments) {
      el("segments").append(node("p", `${(s.start_ms/1000).toFixed(2)}~${(s.end_ms/1000).toFixed(2)}초 · ${s.text}`));
    }
    const labels = {WORD_TIMESTAMPS_UNAVAILABLE:"단어 시각 없음: 원본 구간 유지", TEXT_LIMIT:"줄수·글자수 초과", DURATION_LIMIT:"6초 초과", SHORT_DURATION:"표시 시간 짧음", READING_SPEED:"빠른 발화", OVERLAPPING_CUES:"구간 겹침"};
    labels.UNALIGNED_WORD_TIMESTAMPS = "단어 정렬 불일치: 원본 구간 유지";
    for (const cue of subtitles.cues) {
      const p = node("p", `${(cue.start_ms/1000).toFixed(2)}~${(cue.end_ms/1000).toFixed(2)}초\n${cue.lines.join("\n")}${cue.review_required ? "\n검토 필요: " + cue.warnings.map(w => labels[w] || w).join(" · ") : ""}`);
      p.className = "subtitle-cue"; el("subtitle-cues").append(p);
    }
    el("subtitle-state").textContent = subtitles.review_required ? "검토가 필요한 자막이 있습니다. 단어 시각을 추정하거나 내용을 생략하지 않았습니다." : `${subtitles.cues.length}개 표시 자막 · 원본 전사 보존`;
    el("subtitle-download").href = `/analyses/${id}/subtitles.srt?profile=shorts-display-v1`;
    el("subtitle-download").hidden = !subtitles.quality_pass;
    if (showVerification) {
      const link = node("a", "검증 결과");
      link.href = `/verification?analysis=${id}`;
      el("subtitle-state").append(" ", link);
    }
    for(const row of subtitles.blocked_segments||[]){el("subtitle-cues").append(node("p", `검수 필요: ${row.start_ms/1000}~${row.end_ms/1000}s | ${row.text}`));}
    el("transcript").hidden = false;
  } catch (error) {
    if (epoch !== generation) return;
    el("transcript").hidden = false;
    el("subtitle-state").textContent = `자막 조회에 실패했습니다. ${error.message}`;
    el("refresh").hidden = false;
  }
}
const analysisStages = {
  queued: {label: "대기", percent: 0},
  download: {label: "영상 준비", percent: 10},
  audio: {label: "음성 준비", percent: 30, transcriptionOnly: 40},
  transcription: {label: "음성 전사", percent: 45, transcriptionOnly: 70},
  proposal: {label: "후보 제안", percent: 70},
  scoring: {label: "후보 채점", percent: 90},
  complete: {label: "완료"},
};

function showWaiting(percent) {
  const progress = el("analysis-progress");
  if (percent === undefined) progress.removeAttribute("value");
  else progress.value = percent;
  el("analysis-percent").textContent = percent === undefined ? "" : `${percent}%`;
  el("analysis-waiting").hidden = false;
}

async function poll(id, epoch) {
  try {
    const data = await request(`/analyses/${id}`);
    if (epoch !== generation) return;
    el("refresh").hidden = true;
    const stage = analysisStages[data.stage];
    const label = stage?.label || data.stage;
    if (data.status === "failed") {
      el("analysis-waiting").hidden = true;
      el("analysis-state").textContent = `${label} 단계에서 실패했습니다. ${data.error.message} (${data.error.code})`;
      el("download-recovery").hidden = data.error.code !== "DOWNLOAD_FAILED";
      if (data.stage === "proposal" || data.stage === "scoring") {
        if (data.stage === "scoring") el("analysis-state").textContent += " 음성 전사와 후보 제안은 완료됐습니다.";
        else el("analysis-state").textContent += " 음성 전사는 완료됐습니다.";
        el("transcript").open = true;
        await renderTranscript(id, epoch, false);
      }
      return;
    }
    el("analysis-state").textContent = `${label} · ${data.analysis_basis}`;
    if (data.status === "succeeded") {
      el("analysis-waiting").hidden = true;
      el("analysis-state").textContent = `100% 완료 · ${data.analysis_basis}`;
      window.loadTranscriptReview(id);
      if (data.config?.mode === "transcription") {
        el("transcript").open = true;
        await renderTranscript(id, epoch);
        if (epoch !== generation) return;
        el("analysis-state").textContent += data.outcome === "NO_SPEECH" ? " · 인식된 대화가 없습니다." : " · 전사 완료 · 추천 AI 호출 없음";
        return;
      }
      if (!data.candidates.length) el("analysis-state").textContent += data.outcome === "NO_SPEECH" ? " · 인식된 대화가 없습니다." : " · 기준에 맞는 추천 구간이 없습니다.";
      render(data);
      if (data.config?.asr_version) await renderTranscript(id, epoch);
    } else {
      const percent = data.config?.mode === "transcription" ? stage?.transcriptionOnly ?? stage?.percent : stage?.percent;
      showWaiting(percent);
      timer = setTimeout(() => poll(id, epoch), 2000);
    }
  } catch (error) {
    if (epoch !== generation) return;
    el("analysis-state").textContent = `상태 조회에 실패했습니다. 분석 실패를 의미하지 않습니다. ${error.message}`;
    el("refresh").hidden = false;
  }
}
function load() {
  window.clearTranscriptReview();
  clearTimeout(timer); generation += 1;
  currentId = new URL(location.href).searchParams.get("analysis");
  selection += 1; chosen = null;
  preview.pause(); preview.removeAttribute("src"); preview.load();
  el("candidate-workspace").hidden = true;
  el("analysis-waiting").hidden = true;
  el("download-recovery").hidden = true;
  el("new-project").hidden = Boolean(currentId);
  el("projects").hidden = Boolean(currentId);
  el("analysis-state").textContent = "분석 상태를 확인하고 있습니다.";
  el("candidates").replaceChildren(); el("analysis-panel").hidden = !currentId;
  el("segments").replaceChildren(); el("subtitle-cues").replaceChildren(); el("subtitle-download").hidden = true; el("transcript").hidden = true;
  el("transcript").open = false;
  if (!currentId) return;
  if (!uuid.test(currentId)) { el("analysis-state").textContent = "분석 번호가 올바르지 않습니다."; return; }
  showWaiting();
  poll(currentId, generation);
}
async function submitAnalysis(pending) {
  if(submitting)return;
  const epoch = generation;
  submitting=true;pendingControls();el("message").textContent="";
  try {
    const result=await request("/analyses",pending.body);
    if (epoch !== generation) return;
    sessionStorage.removeItem(pendingKey);
    history.pushState({}, "", `/recommendations?analysis=${encodeURIComponent(result.analysis_id)}`); load();
    el("analysis-title").focus();
  } catch (error) {
    if(error.status===422 || error.status===410)sessionStorage.removeItem(pendingKey);
    if(epoch===generation)el("message").textContent=`${error.message} 접수 여부를 확인하지 못했다면 이전 접수 상태를 조회하세요. 자동 재접수하지 않습니다.`;
  }finally{submitting=false;pendingControls();}
}
async function recoverAnalysis(){
  const pending=pendingAnalysis();if(!pending||submitting)return;
  submitting=true;pendingControls();const epoch=generation;
  try{
    const result=await request(`/analysis-requests/${pending.body.request_id}`);
    if(epoch!==generation)return;
    sessionStorage.removeItem(pendingKey);history.replaceState({},"",`/recommendations?analysis=${result.analysis_id}`);load();
    el("analysis-title").focus();
  }catch(error){
    if(error.status===410)sessionStorage.removeItem(pendingKey);
    if(epoch===generation)el("message").textContent=`${error.message} 새 분석을 자동으로 만들지 않습니다. 필요하면 앞서 입력한 내용을 같은 요청 번호로 다시 접수하세요.`;
  }finally{submitting=false;pendingControls();}
}
el("analysis-form").onsubmit = event => {
  event.preventDefault();if(submitting||pendingAnalysis())return;
  const pending={created_at:Date.now(),body:{request_id:requestId(),mode:el("mode").value,
    ...(window.uploadedAssetId?{asset_id:window.uploadedAssetId}:{url:el("url").value}),genre:el("genre").value,purpose:el("purpose").value}};
  sessionStorage.setItem(pendingKey,JSON.stringify(pending));submitAnalysis(pending);
};
el("recover-analysis").onclick=recoverAnalysis;
el("resubmit-analysis").onclick=()=>{const pending=pendingAnalysis();if(!pending||submitting)return;if(Date.now()-pending.created_at>=7*86400000){el("message").textContent="접수 확인 기간이 지났습니다. 기존 자료와 작업을 먼저 확인하세요.";return;}submitAnalysis(pending);};
el("refresh").onclick = () => load();
el("mode").onchange = () => {
  const transcription = el("mode").value === "transcription";
  el("analyze").textContent = transcription ? "음성 전사 시작" : "하이라이트 추천받기";
  el("genre").disabled = transcription; el("purpose").disabled = transcription;
};
el("mode").onchange();
addEventListener("popstate", load);
load();
pendingControls();
if(!currentId && pendingAnalysis())recoverAnalysis();
