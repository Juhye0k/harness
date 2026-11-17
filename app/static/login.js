"use strict";
const pending = new URLSearchParams(location.search).get('pending');
if (pending && /^[a-f0-9-]{36}$/.test(pending)) document.getElementById('pending').textContent = `운영자 승인이 필요합니다. 요청 번호: ${pending}`;
