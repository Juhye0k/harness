"use strict";
const $ = (id) => document.getElementById(id);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const states = {
  pending: ["접수 확인 중", "작업 전달을 확인하고 있어요. 이 주소에서 다시 확인할 수 있어요."],
  queued: ["추출 대기 중", "영상을 처리할 차례를 기다리고 있어요."],
  running: ["영상을 추출하고 있어요", "영상 길이와 네트워크 상태에 따라 시간이 걸릴 수 있어요."],
  succeeded: ["10초 영상이 준비됐어요", "미리보기로 확인한 후 MP4로 내려받으세요."],
  failed: ["영상 추출에 실패했어요", "입력 영상과 시작 시간을 확인해 주세요."],
};
let jobId = null;
let generation = 0;
let timer;
let submitting = false;
let downloading = false;
let currentDownload = null;
function message(id, text) { $(id).textContent = text; $(id).hidden = !text; }
async function request(url, options = {}) {
  return fetch(url, {...options, signal: AbortSignal.timeout(15000), cache: "no-store"});
}
function resetResult() {
  currentDownload = null;
  $("result").hidden = true;
  $("preview").removeAttribute("src");
  $("preview").load();
  message("media-message", "");
}
async function poll(version) {
  if (version !== generation || !jobId) return;
  clearTimeout(timer);
  $("retry").hidden = true;
  try {
    const response = await request(`/jobs/${jobId}`);
    if (version !== generation) return;
    if (response.status === 404) {
      $("job-title").textContent = "작업을 찾을 수 없어요";
      $("job-description").textContent = "주소의 작업 번호를 확인해 주세요.";
      message("connection-message", "");
      resetResult();
      return;
    }
    if (!response.ok) throw new Error("query");
    const job = await response.json();
    if (version !== generation) return;
    if (!states[job.status] || job.job_id !== jobId) throw new Error("response");
    const [title, description] = states[job.status];
    $("job-title").textContent = title;
    $("job-description").textContent = description;
    message("connection-message", "");
    if (job.status === "failed") {
      $("job-description").textContent = job.error?.message || description;
      resetResult();
    } else if (job.status === "succeeded") {
      if (job.duration_seconds && job.duration_seconds !== 10) $("job-title").textContent = "추천 구간 영상이 준비됐어요";
      currentDownload = `/jobs/${jobId}/download`;
      $("preview").src = currentDownload;
      $("result").hidden = false;
      const uploadLink = $("youtube-upload");
      if (uploadLink) { uploadLink.href = `/sns?job=${jobId}`; uploadLink.hidden = false; }
      const duration = job.result?.media?.duration;
      $("result-info").textContent = Number.isFinite(duration) ? `${duration.toFixed(1)}초 · MP4` : "MP4 영상";
    } else {
      timer = setTimeout(() => poll(version), 2000);
    }
  } catch {
    if (version !== generation) return;
    message("connection-message", "상태를 조회하지 못했어요. 영상 작업의 실패를 의미하지는 않아요. 연결을 확인하고 다시 조회해 주세요.");
    $("retry").hidden = false;
  }
}
function restore() {
  generation += 1;
  clearTimeout(timer);
  resetResult();
  message("connection-message", "");
  $("retry").hidden = true;
  jobId = new URL(location.href).searchParams.get("job");
  $("input-panel").hidden = Boolean(jobId);
  $("job-panel").hidden = !jobId;
  $("job-title").textContent = "작업 조회 중";
  $("job-description").textContent = "작업 상태를 확인하고 있어요.";
  $("job-id").textContent = jobId || "";
  if (jobId && uuid.test(jobId)) poll(generation);
  else if (jobId) {
    $("job-title").textContent = "작업 주소가 올바르지 않아요";
    $("job-description").textContent = "작업 번호가 포함된 주소를 확인해 주세요.";
  }
}
$("extract-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submitting) return;
  const start = Number($("start").value);
  if (!Number.isFinite(start) || start < 0) return;
  submitting = true;
  $("submit").disabled = true;
  $("submit").textContent = "작업 접수 중…";
  message("submit-message", "");
  const version = generation;
  try {
    const response = await request("/jobs/video-extractions", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url: $("video-url").value.trim(), start_seconds: start}),
    });
    const data = await response.json();
    if (version !== generation) return;
    if (uuid.test(data.job_id || "") && (response.ok || response.status === 503)) {
      history.pushState(null, "", `/?job=${data.job_id}`);
      restore();
    } else if (response.status === 422) {
      message("submit-message", "영상 링크와 시작 시간을 확인해 주세요.");
    } else throw new Error("submit");
  } catch {
    if (version === generation) message("submit-message", "접수 결과를 확인하지 못했어요. 작업이 등록됐을 수도 있으니 바로 반복 요청하지 말고 서버 상태를 확인해 주세요.");
  } finally {
    submitting = false;
    $("submit").disabled = false;
    $("submit").textContent = "10초 영상 만들기 ↗";
  }
});
$("retry").addEventListener("click", () => poll(generation));
$("preview").addEventListener("error", () => {
  if (currentDownload) message("media-message", "미리보기를 불러오지 못했어요. 다운로드로 파일을 확인해 주세요.");
});
$("download").addEventListener("click", async () => {
  if (!currentDownload || downloading) return;
  downloading = true;
  $("download").disabled = true;
  const version = generation;
  const name = jobId;
  try {
    const response = await request(currentDownload);
    if (!response.ok) throw new Error(response.status === 410 ? "gone" : "download");
    const blob = await response.blob();
    if (version !== generation) return;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${name}.mp4`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    message("media-message", "");
  } catch (error) {
    if (version === generation) message("media-message", error.message === "gone" ? "결과 파일을 찾을 수 없어요. 새 작업으로 다시 추출해 주세요." : "다운로드하지 못했어요. 연결을 확인한 후 다시 시도해 주세요.");
  } finally {
    downloading = false;
    $("download").disabled = false;
  }
});
window.addEventListener("popstate", restore);
restore();
