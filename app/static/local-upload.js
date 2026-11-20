"use strict";
(() => {
  const uuid=/^[a-f0-9-]{36}$/i;
  let assetId=new URL(location.href).searchParams.get('upload'),busy=false,timer;
  const max=500*1024*1024;
  async function json(url,options={}) {
    const response=await fetch(url,{...options,cache:'no-store'});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error?.message || `요청 실패 (${response.status})`);
    return data;
  }
  function init(){
    const form=document.getElementById('extract-form') || document.getElementById('analysis-form');
    if(!form)return;
    const url=document.getElementById('video-url') || document.getElementById('url');
    const block=document.createElement('fieldset');
    const title=document.createElement('legend');title.textContent='내 컴퓨터의 영상';
    const file=document.createElement('input');file.type='file';file.accept='.mp4,.webm,.mov,.mkv';file.setAttribute('aria-label','업로드할 영상 파일');
    const button=document.createElement('button');button.type='button';button.textContent='선택한 파일 업로드';
    const status=document.createElement('p');status.setAttribute('role','status');
    const retry=document.createElement('button');retry.type='button';retry.textContent='업로드 상태 다시 조회';retry.hidden=true;
    const clear=document.createElement('button');clear.type='button';clear.textContent='링크 입력으로 전환';clear.hidden=true;
    const note=document.createElement('p');note.className='hint';note.textContent='MP4/WebM · 최대 500MiB·20분. 전송 후 영상 검사만 수행하며 AI 분석은 실행 버튼을 누를 때 시작합니다.';
    block.append(title,file,button,note,status,retry,clear);
    const uploadOptions=document.getElementById('local-upload-options');
    if(uploadOptions){uploadOptions.append(block);uploadOptions.open=Boolean(assetId)||location.hash==='#local-upload-options';}
    else form.prepend(block);
    const submit=document.getElementById('submit') || document.getElementById('analyze');
    function lock(value){url.required=!value;url.disabled=value;submit.disabled=value;clear.hidden=!value;}
    function remember(id){assetId=id;const next=new URL(location.href);if(id)next.searchParams.set('upload',id);else next.searchParams.delete('upload');history.replaceState(null,'',next);}
    async function poll(){
      clearTimeout(timer);retry.hidden=true;
      try{
        const data=await json(`/assets/${assetId}/upload`);
        if(data.status==='ready'){
          window.uploadedAssetId=assetId;submit.disabled=false;status.textContent='원본 검증 완료. 시작 시간이나 분석 조건을 정하고 실행하세요.';busy=false;button.disabled=false;
        }else if(data.status==='failed'){
          status.textContent=`업로드 처리 실패 (${data.error_code}). 파일을 확인한 뒤 새로 선택하세요.`;busy=false;button.disabled=false;
        }else if(['created','receiving'].includes(data.status)&&!busy){
          status.textContent='전송 완료를 확인할 수 없습니다. 새로고침은 파일을 다시 보내지 않습니다. 새 파일을 선택해 전송하세요.';
        }else{status.textContent='전송 완료 · 영상 형식과 길이를 검사하고 있습니다.';timer=setTimeout(poll,1500);}
      }catch(e){status.textContent=`상태 조회 오류: ${e.message} 업로드 실패를 의미하지 않습니다.`;retry.hidden=false;}
    }
    file.onchange=()=>{if(!busy){window.uploadedAssetId=null;if(file.files.length)url.required=false;}};
    form.addEventListener('submit',event=>{
      if((assetId || file.files.length)&&!window.uploadedAssetId){event.preventDefault();event.stopImmediatePropagation();status.textContent='먼저 파일 업로드와 원본 검증을 완료하세요.';}
    },true);
    button.onclick=async()=>{
      if(busy)return;
      const selected=file.files[0];if(!selected){status.textContent='영상 파일을 선택하세요.';return;}
      if(!selected.size||selected.size>max){status.textContent='빈 파일 또는 500MiB 초과 파일은 업로드할 수 없습니다.';return;}
      busy=true;button.disabled=true;window.uploadedAssetId=null;lock(true);
      try{
        const receipt=await json('/assets/uploads',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({size_bytes:selected.size})});
        remember(receipt.asset_id);
        const auth=await json('/auth/me');
        await new Promise((resolve,reject)=>{
          const xhr=new XMLHttpRequest();xhr.open('PUT',receipt.upload_url);xhr.timeout=600000;
          xhr.setRequestHeader('Content-Type','application/octet-stream');if(auth.csrf)xhr.setRequestHeader('X-CSRF-Token',auth.csrf);
          xhr.upload.onprogress=e=>{status.textContent=e.lengthComputable?`파일 전송 중 ${Math.floor(e.loaded/e.total*100)}%`:'파일 전송 중…';};
          xhr.onload=()=>xhr.status===202?resolve():reject(new Error('전송 결과를 확인하지 못했습니다. 상태를 조회하세요.'));
          xhr.onerror=xhr.ontimeout=()=>reject(new Error('전송 연결이 끊겼습니다. 자동으로 다시 보내지 않습니다.'));
          xhr.send(selected);
        });
        await poll();
      }catch(e){status.textContent=e.message;retry.hidden=!assetId;busy=false;button.disabled=false;}
    };
    retry.onclick=poll;
    clear.onclick=()=>{if(busy)return;clearTimeout(timer);remember(null);window.uploadedAssetId=null;file.value='';lock(false);status.textContent='';};
    if(assetId&&uuid.test(assetId)){lock(true);poll();}
  }
  document.addEventListener('DOMContentLoaded',init);
})();
