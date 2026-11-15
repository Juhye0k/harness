"use strict";
const el = (id) => document.getElementById(id);
let generation = 0, timer, currentId;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
async function request(url, body) {
  const response = await fetch(url, {method: body ? "POST" : "GET",
    headers: body ? {"Content-Type": "application/json"} : {},
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(15000)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || `조회 오류 (${response.status})`);
  return data;
}
function node(tag, text) { const n = document.createElement(tag); n.textContent = text; return n; }
function render(data, epoch) {
  el("candidates").replaceChildren();
  for (const item of data.candidates) {
    const article = document.createElement("article"); article.className = "candidate";
    article.append(node("h3", `${item.rank}. ${item.title}`),
      node("p", `${(item.start_ms/1000).toFixed(1)}~${(item.end_ms/1000).toFixed(1)}초 · 편집 적합도 ${item.score}/100`),
      node("p", item.reason));
    const labels = {hook: "도입", completeness: "완결성", context_independence: "독립성", memorable: "인상", editability: "편집성"};
    article.append(node("p", Object.entries(item.scores).map(([k,v]) => `${labels[k]} ${v}/4`).join(" · ")));
    const details = document.createElement("details"); details.append(node("summary", "전사 내용과 근거 보기"));
    details.append(node("p", item.segments.map(s => s.text).join(" ")),
      node("p", `근거: ${item.evidence_ids.join(", ")}`)); article.append(details);
    if (item.export_job_id) {
      const link = node("a", "추출 상태 · 미리보기 · 다운로드 →");
      link.href = `/?job=${encodeURIComponent(item.export_job_id)}`; article.append(link);
    } else {
      const button = node("button", "이 구간 추출하기"); button.type = "button";
      button.onclick = async () => {
        button.disabled = true;
        try {
          const result = await request(`/analyses/${data.analysis_id}/candidates/${item.id}/exports`, {});
          if (epoch !== generation) return;
          // Existing video page restores the persisted job and handles preview/download.
          location.assign(`/?job=${encodeURIComponent(result.job_id)}`);
        } catch (error) {
          if (epoch !== generation) return;
          el("message").textContent = `${error.message} 상태를 다시 조회해 기존 추출 작업을 확인하세요.`;
          el("refresh").hidden = false;
        }
      };
      article.append(button);
    }
    el("candidates").append(article);
  }
}
async function poll(id, epoch) {
  try {
    const data = await request(`/analyses/${id}`);
    if (epoch !== generation) return;
    el("refresh").hidden = true;
    const stages = {queued:"대기", download:"영상 준비", audio:"음성 준비", transcription:"음성 전사", proposal:"구간 제안", scoring:"후보 평가", complete:"완료"};
    el("analysis-state").textContent = data.status === "failed"
      ? `${data.error.message} (${data.error.code})`
      : `${stages[data.stage] || data.stage} · ${data.analysis_basis}`;
    if (data.status === "succeeded") {
      if (!data.candidates.length) el("analysis-state").textContent += data.outcome === "NO_SPEECH" ? " · 인식된 대화가 없습니다." : " · 기준에 맞는 추천 구간이 없습니다.";
      render(data, epoch);
    } else if (data.status !== "failed") timer = setTimeout(() => poll(id, epoch), 2000);
  } catch (error) {
    if (epoch !== generation) return;
    el("analysis-state").textContent = `상태 조회에 실패했습니다. 분석 실패를 의미하지 않습니다. ${error.message}`;
    el("refresh").hidden = false;
  }
}
function load() {
  clearTimeout(timer); generation += 1;
  currentId = new URL(location.href).searchParams.get("analysis");
  el("candidates").replaceChildren(); el("analysis-panel").hidden = !currentId;
  if (!currentId) return;
  if (!uuid.test(currentId)) { el("analysis-state").textContent = "분석 번호가 올바르지 않습니다."; return; }
  poll(currentId, generation);
}
el("analysis-form").onsubmit = async (event) => {
  event.preventDefault(); if (el("analyze").disabled) return;
  const epoch = generation;
  el("analyze").disabled = true; el("message").textContent = "";
  try {
    const result = await request("/analyses", {url:el("url").value, genre:el("genre").value, purpose:el("purpose").value});
    if (epoch !== generation) return;
    history.pushState({}, "", `/recommendations?analysis=${encodeURIComponent(result.analysis_id)}`); load();
  } catch (error) {
    if (epoch === generation) el("message").textContent = `${error.message} 접수 여부가 불명확하면 자동으로 다시 요청하지 마세요.`;
  } finally { el("analyze").disabled = false; }
};
el("refresh").onclick = () => load();
addEventListener("popstate", load);
load();
