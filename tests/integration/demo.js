"use strict";
const frame=document.getElementById('studio'), message=document.getElementById('demo-message');
document.getElementById('demo-sample').onclick=()=>{
  const fill=()=>{
    const doc=frame.contentDocument;
    doc.getElementById('url').value='https://fixture.example/analysis.mp4';
    const mode=doc.getElementById('mode');mode.value='recommendation';mode.dispatchEvent(new Event('change'));
    message.textContent='샘플 링크를 입력했습니다. 아래에서 하이라이트 추천받기를 누르세요.';
  };
  if(frame.contentWindow.location.pathname==='/recommendations')fill();
  else {frame.addEventListener('load',fill,{once:true});frame.src='/recommendations';}
};
document.getElementById('demo-channel').onclick=async event=>{
  event.target.disabled=true;
  try{
    const session=await (await fetch('/sns/session')).json();
    const response=await fetch('/sns/youtube/connect',{method:'POST',headers:{'X-SNS-CSRF':session.csrf}});
    if(!response.ok)throw new Error('데모 채널 준비 설정을 확인하세요.');
    const {authorization_url}=await response.json();
    const state=new URL(authorization_url).searchParams.get('state');
    await fetch('/sns/youtube/callback?'+new URLSearchParams({state,code:'fixture-code'}));
    const accounts=await (await fetch('/sns/accounts')).json();
    if(!accounts.length)throw new Error('데모 계정 연결을 확인하지 못했습니다.');
    message.textContent='데모 채널을 연결했습니다. 이 환경의 업로드는 외부로 전송하지 않습니다.';
    if(frame.contentWindow.location.pathname==='/sns')frame.contentWindow.location.reload();
  }catch(error){message.textContent=error.message;}
  finally{event.target.disabled=false;}
};
