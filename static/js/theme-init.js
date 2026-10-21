// Apply the saved appearance before the first paint. No network or secrets.
try {
  const owner=Number(localStorage.getItem('lexi:active-account'));
  const key=Number.isInteger(owner)&&owner>0?`lexi:account:${owner}:v1`:'lexi:v1';
  const saved = JSON.parse(localStorage.getItem(key) || '{}');
  if (['noir', 'studio', 'experimental'].includes(saved.theme)) {
    document.documentElement.dataset.theme = saved.theme;
  }
  const entryTheme=localStorage.getItem('lexi:entry-theme');
  document.documentElement.dataset.entryTheme=['noir','studio','experimental'].includes(entryTheme)?entryTheme:
    ['noir','studio','experimental'].includes(saved.theme)?saved.theme:'studio';
  if (saved.reduceMotion === true) document.documentElement.classList.add('reduce-motion');
} catch { /* Storage may be unavailable; Noir remains the default. */ }

