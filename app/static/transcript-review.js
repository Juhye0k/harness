/* Human decisions are separate from immutable transcripts and subtitle exports. */
let reviewEpoch = 0;
window.clearTranscriptReview = () => {
  reviewEpoch++;
  const previous = document.querySelector("#review-panel audio");
  if (previous) {previous.pause(); previous.removeAttribute("src"); previous.load();}
  document.getElementById("review-panel")?.remove();
};
window.loadTranscriptReview = async (id) => {
  window.clearTranscriptReview();
  const epoch = reviewEpoch;
  const panel = document.createElement("section"); panel.id = "review-panel";
  document.getElementById("analysis-panel").append(panel);
  const element = (tag, text) => {const n=document.createElement(tag); n.textContent=text; return n;};
  const status = element("p", "検査中".replace("検査中", "검수 정보 조회 중…"));
  status.setAttribute("role", "status"); panel.append(element("h3", "전사 검수"), status);
  const api = async (path, body) => {
    const response = await fetch(path, body ? {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
    if (!response.ok) throw new Error(response.status === 409 ? "저장 충돌입니다. 검수 정보를 다시 조회하세요." : "검수 요청 실패. 입력을 보존했습니다.");
    return response.json();
  };
  try {
    const url = `/analyses/${encodeURIComponent(id)}`;
    const data = await api(`${url}/transcript-review`);
    if (epoch !== reviewEpoch) return;
    const audio = document.createElement("audio"); audio.controls=true; audio.preload="none";
    audio.src=`${url}/review-audio`; audio.style.maxWidth="100%";
    let stopAt = null;
    audio.addEventListener("timeupdate", () => {if (stopAt !== null && audio.currentTime >= stopAt) audio.pause();});
    audio.addEventListener("error", () => {status.textContent="저장된 음성을 재생할 수 없습니다. 자동 재전사하지 않습니다.";});
    panel.append(element("p", "의심 신호는 오류 확정이 아닙니다. 표시 문제와 인식 문제를 구분해 확인하세요."), audio);
    const filter=document.createElement("select"); filter.setAttribute("aria-label", "검수 구간 필터");
    for (const [value,label] of [["flagged","의심 구간"],["all","전체 구간"],["unreviewed","미검수 구간"],["sample","비표시 구간 표본"]]) {
      const option=element("option",label); option.value=value; filter.append(option);
    }
    const download=element("button","검수 보고서 JSON 다운로드"); download.type="button";
    download.onclick=()=>{const a=document.createElement("a"); const blob=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"})); a.href=blob; a.download=`transcript-review-${id}.json`; a.click(); setTimeout(()=>URL.revokeObjectURL(blob),1000);};
    const reload=element("button","검수 다시 조회"); reload.type="button"; reload.onclick=()=>window.loadTranscriptReview(id);
    const list=document.createElement("div"); panel.append(filter,download,reload,list);
    const labels={LOW_CONFIDENCE:"낮은 인식 신뢰도",POSSIBLE_NON_SPEECH:"무음 관련 복합 신호",COMPRESSION_REPETITION:"압축 비율상 반복 의심",ADJACENT_REPETITION:"이전 구간과 같은 문구"};
    const drafts=new Map();
    const render=()=>{
      data.unreviewed=data.segments.filter(s=>s.decision===null).length;
      status.textContent=`전체 ${data.total}개 · 의심 ${data.flagged}개 · 미검수 ${data.unreviewed}개 · 신뢰도 정보 ${data.quality_available}/${data.total}개 · 정확도 점수 아님`;
      list.replaceChildren();
      for (const row of data.segments) {
        if (filter.value==="flagged" && row.priority==="none" || filter.value==="unreviewed" && row.decision!==null) continue;
        if (filter.value==="sample" && !data.unflagged_sample_ids.includes(row.id)) continue;
        const card=document.createElement("article"); card.className="subtitle-cue"; card.dataset.segmentId=row.id; card.id=`review-${row.id}`;
        card.append(element("p",`${(row.start_ms/1000).toFixed(2)}~${(row.end_ms/1000).toFixed(2)}초 · ${row.priority}`),element("p",row.text));
        card.append(element("p",`인식: ${row.recognition_reasons.map(r=>labels[r]||r).join(" · ")||"탐지 신호 없음"} / 표시: ${row.display_reasons.join(" · ")||"없음"}`));
        card.append(element("p",`관측값: ${JSON.stringify(row.quality)} / 평가 불가: ${row.unavailable_metrics.join(", ")||"없음"}`));
        const play=element("button","앞뒤 2초 듣기"); play.type="button";
        play.onclick=()=>{
          const start=Math.max(0,row.start_ms/1000-2);
          const seek=()=>{stopAt=Math.min(row.end_ms/1000+2,audio.duration); audio.currentTime=start; audio.play().catch(()=>{status.textContent="재생할 수 없습니다. 저장된 음성을 확인하세요.";});};
          if (audio.readyState>=1) seek(); else {audio.addEventListener("loadedmetadata",seek,{once:true}); audio.load();}
        };
        const note=document.createElement("textarea"); note.maxLength=1000; note.value=drafts.get(row.id)??row.note; note.setAttribute("aria-label",`${row.id} 검수 메모`);
        note.oninput=()=>drafts.set(row.id,note.value);
        const result=element("p",row.decision ? `저장된 판정: ${row.decision}` : "미검수"); result.setAttribute("role","status");
        const buttons=[];
        for (const [decision,label] of [["error","오류 있음"],["ok","이상 없음"],["uncertain","판단 어려움"]]) {
          const button=element("button",label); button.type="button"; buttons.push(button);
          button.onclick=async()=>{
            buttons.forEach(b=>b.disabled=true); note.disabled=true;
            try {
              const saved=await api(`${url}/transcript-review/${encodeURIComponent(row.id)}`,{transcript_version:data.transcript_version,policy_version:data.policy_version,revision:row.revision,decision,note:note.value});
              if(epoch!==reviewEpoch)return;
              Object.assign(row,saved); drafts.delete(row.id); render();
            } catch(error) {result.textContent=error.message;}
            finally {buttons.forEach(b=>b.disabled=false); note.disabled=false;}
          };
        }
        card.append(play,note,...buttons,result); list.append(card);
      }
    };
    filter.onchange=render; if(location.hash.startsWith('#review-'))filter.value='all'; render(); if(location.hash.startsWith('#review-'))document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch(error) {if(epoch===reviewEpoch)status.textContent=`${error.message} 전사 완료 상태와 별개입니다.`;}
};
