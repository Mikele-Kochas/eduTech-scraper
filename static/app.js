const runBtn = document.getElementById('runBtn');
const loader = document.getElementById('loader');
const cards = document.getElementById('cards');
const modal = document.getElementById('modal');
const closeModal = document.getElementById('closeModal');
const modalBody = document.getElementById('modalBody');
const logsEl = document.getElementById('logs');

function kv(k, v){
  return `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function renderCard(item){
  const title = item.gemini_tytul || item.tytuł || 'Brak tytułu';
  const date = item.data || '';
  const el = document.createElement('div');
  el.className = 'card';
  el.innerHTML = `<h3>${title}</h3><div class="meta">${date}</div><div>${(item.gemini_tresc||item.treść||'').slice(0,180)}...</div>`;
  el.addEventListener('click', ()=>{
    const body = [
      kv('Tytuł (AI)', item.gemini_tytul || '—'),
      kv('Tytuł (oryg.)', item.tytuł || '—'),
      kv('Data', item.data || '—'),
      kv('Link', `<a href="${item.link}" target="_blank">${item.link}</a>`),
      kv('Treść (AI)', (item.gemini_tresc||'—').replace(/\n\n/g,'<br/><br/>')),
      kv('Treść (oryg.)', (item.treść||'—').replace(/\n\n/g,'<br/><br/>')),
    ].join('');
    modalBody.innerHTML = body;
    modal.classList.remove('hidden');
  });
  return el;
}

runBtn.addEventListener('click', async ()=>{
  runBtn.disabled = true;
  loader.classList.remove('hidden');
  cards.innerHTML = '';
  try {
    const res = await fetch('/api/run', { method: 'POST' });
    const data = await res.json();
    data.forEach(item => cards.appendChild(renderCard(item)));
  } catch (e) {
    alert('Błąd podczas generowania. Sprawdź logi serwera.');
  } finally {
    loader.classList.add('hidden');
    runBtn.disabled = false;
  }
});

document.getElementById('closeModal').addEventListener('click', ()=>{
  modal.classList.add('hidden');
});

modal.addEventListener('click', (e)=>{
  if(e.target === modal){ modal.classList.add('hidden'); }
});

// SSE logs
try{
  const es = new EventSource('/api/logs/stream');
  es.onmessage = (e)=>{
    if(!logsEl) return;
    logsEl.textContent += e.data + '\n';
    logsEl.scrollTop = logsEl.scrollHeight;
  };
}catch(e){
  // ignore
}


