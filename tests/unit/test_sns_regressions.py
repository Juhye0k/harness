"""Standalone logging and browser draft identity, without provider or infrastructure calls."""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from app.adapters.sns_logging import (
    GoogleHttpFilter,
    SnsAccessFilter,
    install_sns_logging,
)

ROOT = Path(__file__).resolve().parents[2]


def test_logging_guards_are_idempotent_and_keep_unrelated_filters(monkeypatch):
    unrelated = logging.Filter()
    access, http = logging.getLogger("uvicorn.access"), logging.getLogger("httpx")
    monkeypatch.setattr(access, "filters", [unrelated])
    monkeypatch.setattr(http, "filters", [unrelated])
    install_sns_logging()
    install_sns_logging()
    assert sum(isinstance(f, SnsAccessFilter) for f in access.filters) == 1
    assert sum(isinstance(f, GoogleHttpFilter) for f in http.filters) == 1
    assert unrelated in access.filters and unrelated in http.filters


def test_standalone_worker_redacts_actual_httpx_mock_request_without_api_import():
    code = """
import io
import logging
import socket
import sys
from types import SimpleNamespace

def no_network(*args, **kwargs):
    raise AssertionError('Unexpected network connection')

socket.socket.connect = no_network
from app import config
config.get_settings = lambda: SimpleNamespace(redis_url='redis://localhost:6379/0')
import app.worker
assert 'app.main' not in sys.modules
from app.adapters.sns_logging import GoogleHttpFilter, install_sns_logging
install_sns_logging()
install_sns_logging()
logger = logging.getLogger('httpx')
assert sum(isinstance(f, GoogleHttpFilter) for f in logger.filters) == 1
stream = io.StringIO()
logger.addHandler(logging.StreamHandler(stream))
logger.setLevel(logging.INFO)
logger.propagate = False
import httpx
from app.adapters.youtube_upload import YouTubeProvider
provider = YouTubeProvider(SimpleNamespace(), httpx.MockTransport(
    lambda request: httpx.Response(200, json={'id':'abcdefghijk'})))
provider.request('PUT',
    'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=synthetic-capability',
    content=b'fixture', headers={'Authorization':'Bearer synthetic-token'})
logger.info('unrelated diagnostic remains visible')
assert stream.getvalue().strip() == 'unrelated diagnostic remains visible'
assert 'app.main' not in sys.modules
print('PASS')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"


def test_explicit_draft_edit_renews_request_but_lost_responses_keep_identity():
    # Execute the real UI script with a minimal DOM and fetch fixture. Node is on the
    # CI runner; the existing Deno tool covers the integration image and Windows fallback.
    node = shutil.which("node")
    deno = shutil.which("deno") or str(ROOT / ".tmp/tools/deno/deno.exe")
    program = Path(node or deno)
    assert program.is_file(), "An existing Node or Deno runtime is required"
    setup = r"""
if (!globalThis.crypto) globalThis.crypto = (await import('node:crypto')).webcrypto;
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {
    value:'', hidden:false, checked:false, disabled:false, textContent:'',
    replaceChildren(...children) {
      this.children = children;
      if (children.length) this.value = children[0].value;
    },
    getAttribute() { return null; }
  });
  return elements.get(id);
}
globalThis.document = {getElementById:element, createElement:() => ({})};
globalThis.location = {href:'http://testserver/sns'};
globalThis.history = {replaceState(_state, _title, path) {
  location.href = new URL(path, location.href).href;
}};
const storage = new Map();
globalThis.sessionStorage = {
  getItem:key => storage.get(key) ?? null,
  setItem:(key,value) => storage.set(key,value),
  removeItem:key => storage.delete(key),
};
const accountId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const jobId = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const uploadId = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const posts = [];
let loseResponse = true;
function response(data) { return {status:200, ok:true, json:async()=>data}; }
globalThis.fetch = async (path, options) => {
  if (path === '/sns/session') return response({csrf:'fixture', enabled:true});
  if (path === '/sns/accounts') return response([
    {account_id:accountId, title:'fixture', channel_id:'channel'}]);
  if (path === '/sns/uploads' && options.method === 'POST') {
    const body = JSON.parse(options.body);
    posts.push(body);
    if (loseResponse) { loseResponse = false; throw new Error('response lost'); }
    return response({
      upload_id:uploadId, status:'draft', approval:{...body, output_version:'a'.repeat(64)},
      account:{title:'fixture', channel_id:'channel'}, can_probe:false, video_url:null,
      expires_at: posts.length < 3 ? '2000-01-01T00:00:00Z' : '2099-01-01T00:00:00Z'
    });
  }
  throw new Error('Unexpected request: ' + path);
};
function check(value, message) { if (!value) throw new Error(message); }
"""
    assertions = r"""
await new Promise(resolve => setTimeout(resolve, 0));
element('account').value = accountId;
element('job').value = jobId;
element('title').value = 'unchanged title';
element('privacy').value = 'private';
element('kids').value = 'false';
const submit = () => element('upload-form').onsubmit({preventDefault(){}});
await submit();
check(current === null, 'Lost response must not invent a new draft');
const pending = sessionStorage.getItem('sns.pending');
await submit();
check(posts.length === 2 && posts[0].request_id === posts[1].request_id,
      'Same-body retry after response loss must reuse its request ID');
check(current.expires_at === '2000-01-01T00:00:00Z', 'Fixture must be expired');
busy = true;
element('edit').onclick();
check(current !== null && sessionStorage.getItem('sns.pending') === pending,
      'In-flight action must not discard draft identity');
busy = false;
element('account').value = 'another-account';
element('edit').onclick();
check(current === null && sessionStorage.getItem('sns.pending') === null,
      'Explicit edit must retire the old request ID');
check(element('account').value === accountId, 'Edit must retain the reviewed channel');
await submit();
check(posts.length === 3 && posts[2].request_id !== posts[1].request_id,
      'Same-content edit after expiry must create a fresh draft request');
check(posts[2].title === posts[1].title && posts[2].job_id === posts[1].job_id,
      'Renewing a draft must not require changing its content');
check(current.expires_at === '2099-01-01T00:00:00Z', 'Fresh draft must be reviewable');
const renewed = sessionStorage.getItem('sns.pending');
current.status = 'queued';
element('edit').onclick();
check(current.status === 'queued' && sessionStorage.getItem('sns.pending') === renewed,
      'Queued uploads must not be converted back into drafts');
console.log('PASS');
"""
    script = setup + (ROOT / "app/static/sns.js").read_text("utf-8") + assertions
    command = (
        [str(program), "--input-type=module", "-e", script] if node else [deno, "eval", script]
    )
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"
