const runBtn = document.getElementById('runBtn');
const loader = document.getElementById('loader');
const cards = document.getElementById('cards');
const modal = document.getElementById('modal');
const closeModal = document.getElementById('closeModal');
const modalBody = document.getElementById('modalBody');
const logsEl = document.getElementById('logs');
const exportBtn = document.getElementById('exportBtn');
const apiKeyInput = document.getElementById('apiKeyInput');

let currentData = [];

// Load API key from localStorage
if(localStorage.getItem('gemini_api_key')){
  apiKeyInput.value = localStorage.getItem('gemini_api_key');
}

// Save API key on change
apiKeyInput.addEventListener('change', ()=>{
  if(apiKeyInput.value.trim()){
    localStorage.setItem('gemini_api_key', apiKeyInput.value.trim());
  }
});

function kv(k, v){
  return `<div class="kv"><div class="k">${k}</div><div class="v">${v}</div></div>`;
}

function renderCard(item){
  // Czyszczenie starych pól
  delete item.gemini_tytul;
  
  const title = item.tytuł || 'Brak tytułu';
  const date = item.data || '';
  const el = document.createElement('div');
  el.className = 'card';
  el.innerHTML = `<h3>${title}</h3><div class="meta">${date}</div><div>${(item.gemini_tresc||item.treść||'').slice(0,180)}...</div>`;
  el.addEventListener('click', ()=>{
    const body = [
      kv('Tytuł', item.tytuł || '—'),
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
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKeyInput.value.trim() })
    });
    const data = await res.json();
    currentData = data; // Update global data
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

exportBtn.addEventListener('click', async ()=>{
  if(currentData.length === 0){
    alert('Brak danych do exportu. Uruchom zbieranie najpierw.');
    return;
  }
  exportBtn.disabled = true;
  try {
    const res = await fetch('/api/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentData)
    });
    if(!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aktualnosci_${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    alert('Błąd podczas exportu: ' + e.message);
  } finally {
    exportBtn.disabled = false;
  }
});


