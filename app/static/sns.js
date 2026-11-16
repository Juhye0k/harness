"use strict";
const $ = id => document.getElementById(id);
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const privacyNames = {private: "비공개", unlisted: "일부 공개", public: "공개"};
let csrf = "", current = null, busy = false, timer;
function newRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function notice(text, retry = false) { $("notice").textContent = text; $("reload").hidden = !retry; }
async function api(path, method = "GET", body) {
  const response = await fetch(path, {
    method, cache: "no-store", signal: AbortSignal.timeout(15000),
    headers: {"Content-Type": "application/json", "X-SNS-CSRF": csrf},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) throw new Error(data.error?.message || "요청을 처리하지 못했어요.");
  return data;
}
function render(data) {
  current = data;
  $("review-panel").hidden = false;
  $("upload-form").hidden = true;
  $("review-channel").textContent = `${data.account.title} (${data.account.channel_id})`;
  $("review-title").textContent = data.approval.title;
  $("review-privacy").textContent = privacyNames[data.approval.privacy];
  $("review-kids").textContent = data.approval.made_for_kids ? "예" : "아니요";
  $("review-version").textContent = data.approval.output_version;
  const preview = `/jobs/${data.approval.job_id}/download`;
  if ($("sns-preview").getAttribute("src") !== preview) $("sns-preview").src = preview;
  $("confirmation").hidden = data.status !== "draft";
  $("approved").checked = false;
  $("confirm").disabled = true;
  $("probe").hidden = !data.can_probe;
  $("remote").hidden = !data.video_url;
  if (data.video_url && /^https:\/\/www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}$/.test(data.video_url)) $("remote").href = data.video_url;
  const descriptions = {
    draft: "아직 전송하지 않았어요. 아래 내용을 확인하고 동의해 주세요. 확인은 15분 동안 유효합니다.",
    queued: "업로드 대기 중입니다. 같은 영상을 다시 요청하지 마세요.",
    running: "YouTube에 전송 중입니다. 이 주소에서 상태를 확인하세요.",
    succeeded: "YouTube 업로드가 완료됐어요. 영상 처리 상태는 YouTube에서 확인하세요.",
    failed: "업로드 작업이 실패했어요. 오류와 기존 계정 상태를 확인하세요. 자동 재시도하지 않습니다.",
    unknown: "업로드 성공 여부가 미확정입니다. 중복 게시를 막기 위해 재전송하지 않습니다. YouTube Studio에서도 확인하세요.",
  };
  $("upload-heading").textContent = data.status === "draft" ? "3. 최종 업로드 확인" : "업로드 상태";
  $("upload-state").textContent = descriptions[data.status] || "상태를 확인할 수 없습니다.";
  if (data.error_code) $("upload-state").textContent += ` (${data.error_code})`;
  clearTimeout(timer);
  if (["queued", "running"].includes(data.status)) timer = setTimeout(loadUpload, 1500);
}
async function loadUpload() {
  clearTimeout(timer);
  const id = new URL(location.href).searchParams.get("upload");
  if (!uuid.test(id || "")) return;
  try { render(await api(`/sns/uploads/${id}`)); notice(""); }
  catch { notice("상태를 조회하지 못했어요. 업로드 실패를 의미하지 않습니다. 다시 조회해 주세요.", true); }
}
async function loadAccounts() {
  const accounts = await api("/sns/accounts");
  $("account").replaceChildren(...accounts.map(account => {
    const option = document.createElement("option");
    option.value = account.account_id;
    option.textContent = `${account.title} (${account.channel_id})`;
    return option;
  }));
  $("disconnect").disabled = !accounts.length;
  $("upload-form").hidden = !accounts.length || Boolean(current);
  if (!accounts.length) notice("먼저 업로드할 YouTube 채널을 연결하세요.");
  return accounts;
}
async function start() {
  try {
    const session = await api("/sns/session"); csrf = session.csrf;
    if (!session.enabled) { notice("SNS 업로드가 비활성화돼 있습니다. 개발 설정 안내를 확인하세요."); return; }
    $("account-panel").hidden = false;
    const params = new URL(location.href).searchParams;
    if (params.get("job")) sessionStorage.setItem("sns.job", params.get("job"));
    $("job").value = sessionStorage.getItem("sns.job") || "";
    notice("");
    const accounts = await loadAccounts();
    if (params.get("oauth") === "error") {
      notice(params.get("reason") === "channel_unavailable"
        ? "선택한 Google 계정에서 YouTube 채널을 확인하지 못했어요. YouTube에서 채널을 만들거나 기존 채널이 있는 계정을 선택한 뒤 다시 연결하세요."
        : "계정 연결을 완료하지 못했어요. 다시 연결하세요.");
    } else if (params.get("oauth") === "connected" && accounts.length) {
      notice("YouTube 채널을 연결했어요. 아래에서 영상과 업로드 설정을 확인하세요.");
    }
    await loadUpload();
  } catch { notice("설정을 조회하지 못했어요. 연결과 서버 설정을 확인한 뒤 새로고침하세요.", true); }
}
$("connect").onclick = async () => {
  if (busy) return; busy = true; $("connect").disabled = true;
  try {
    const data = await api("/sns/youtube/connect", "POST");
    const url = new URL(data.authorization_url);
    if (url.origin !== "https://accounts.google.com") throw new Error("계정 연결 주소를 확인하지 못했어요.");
    location.assign(url.href);
  } catch (error) { notice(error.message); busy = false; $("connect").disabled = false; }
};
$("disconnect").onclick = async () => {
  if (busy || !$("account").value) return; busy = true;
  try { await api(`/sns/accounts/${$("account").value}`, "DELETE"); await loadAccounts(); }
  catch (error) { notice(error.message); }
  finally { busy = false; }
};
$("upload-form").onsubmit = async event => {
  event.preventDefault();
  if (busy || !uuid.test($("job").value)) return;
  busy = true; $("prepare").disabled = true;
  try {
    const fields = {account_id: $("account").value, job_id: $("job").value, title: $("title").value,
      privacy: $("privacy").value, made_for_kids: $("kids").value === "true"};
    let pending;
    try { pending = JSON.parse(sessionStorage.getItem("sns.pending") || "null"); } catch { pending = null; }
    const requestId = pending?.fields === JSON.stringify(fields) && uuid.test(pending.id) ? pending.id : newRequestId();
    sessionStorage.setItem("sns.pending", JSON.stringify({id: requestId, fields: JSON.stringify(fields)}));
    const data = await api("/sns/uploads", "POST", {request_id: requestId, ...fields});
    history.replaceState(null, "", `/sns?upload=${data.upload_id}`);
    render(data); notice("");
  } catch (error) { notice(`미리보기를 확인하지 못했어요. ${error.message}`); }
  finally { busy = false; $("prepare").disabled = false; }
};
$("approved").onchange = () => { $("confirm").disabled = !$("approved").checked || busy; };
$("confirm").onclick = async () => {
  if (busy || !current || !$("approved").checked) return;
  busy = true; $("confirm").disabled = true;
  try {
    const data = await api(`/sns/uploads/${current.upload_id}/confirm`, "POST", {confirmed: true, approval: current.approval});
    history.replaceState(null, "", `/sns?upload=${data.upload_id}`); render(data); notice("");
  } catch { notice("접수 결과를 확인하지 못했어요. 등록됐을 수 있으니 상태를 다시 조회하세요.", true); }
  finally { busy = false; }
};
$("edit").onclick = () => {
  $("title").value = current.approval.title;
  $("job").value = current.approval.job_id;
  $("privacy").value = current.approval.privacy;
  $("kids").value = String(current.approval.made_for_kids);
  current = null; $("review-panel").hidden = true; $("upload-form").hidden = false;
  history.replaceState(null, "", "/sns");
};
$("probe").onclick = async () => {
  if (busy || !current) return; busy = true; $("probe").disabled = true;
  try {
    await api(`/sns/uploads/${current.upload_id}/probe`, "POST");
    notice("영상 재전송 없이 상태만 확인하고 있어요.");
    timer = setTimeout(loadUpload, 2000);
  } catch (error) { notice(error.message); }
  finally { busy = false; $("probe").disabled = false; }
};
$("reload").onclick = () => current || new URL(location.href).searchParams.has("upload") ? loadUpload() : start();
start();
