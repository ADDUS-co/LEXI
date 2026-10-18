// Apply the saved appearance before the first paint. No network or secrets.
try {
  const saved = JSON.parse(localStorage.getItem('lexi:v1') || '{}');
  if (['noir', 'studio', 'experimental'].includes(saved.theme)) {
    document.documentElement.dataset.theme = saved.theme;
  }
  if (saved.reduceMotion === true) document.documentElement.classList.add('reduce-motion');
} catch { /* Storage may be unavailable; Noir remains the default. */ }

