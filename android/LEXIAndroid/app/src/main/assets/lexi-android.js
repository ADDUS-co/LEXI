(function () {
  'use strict';
  if (location.origin !== 'https://lexi-m388.onrender.com' || !window.LexiAndroid || window.__lexiAndroidAdapter) return;
  window.__lexiAndroidAdapter = true;

  function visibleWord() {
    var heading = document.querySelector('#main-content #daily-word');
    if (!heading) return null;
    var word = heading.textContent.trim();
    if (word.endsWith('.')) word = word.slice(0, -1);
    return word.trim();
  }
  function feedback(message) {
    var toast = document.querySelector('#toast');
    if (!toast) return;
    toast.textContent = message;
    toast.hidden = false;
    setTimeout(function () { toast.hidden = true; }, 4000);
  }
  window.addEventListener('click', function (event) {
    var button = event.target instanceof Element && event.target.closest('[data-action]');
    if (!button || button.disabled) return;
    var action = button.dataset.action;
    if (action === 'hide-word') window.LexiAndroid.stopSpeech();
    if (!['pronounce', 'share', 'export'].includes(action)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    var word = visibleWord();
    if (action === 'pronounce') {
      if (word) window.LexiAndroid.speak(word);
    } else if (action === 'share') {
      var saved = document.querySelector('#main-content [data-action="save"][data-word]');
      if (!word || !saved) return;
      var meaning = document.querySelector('#main-content .short-definition');
      var url = location.origin + '/#word/' + encodeURIComponent(saved.dataset.word);
      window.LexiAndroid.share(word + (meaning ? ': ' + meaning.textContent.trim() : '') + '\n' + url);
    } else {
      import('/static/js/storage.js').then(function (storage) {
        window.LexiAndroid.exportProgress(JSON.stringify({
          app: 'LEXI', exportedAt: new Date().toISOString(), preferences: storage.readStore(),
        }, null, 2));
      }).catch(function () { feedback('Could not export your progress. Please try again.'); });
    }
  }, true);
  window.addEventListener('lexi:android-speech', function (event) {
    var button = document.querySelector('#main-content .listen-button');
    if (button) button.classList.toggle('is-speaking', Boolean(event.detail && event.detail.speaking));
  });
  window.addEventListener('dblclick', function (event) {
    if (event.target instanceof Element && event.target.closest('[data-flip-surface]')) window.LexiAndroid.stopSpeech();
  }, true);
  document.addEventListener('visibilitychange', function () { if (document.hidden) window.LexiAndroid.stopSpeech(); });
  window.addEventListener('pagehide', function () { window.LexiAndroid.stopSpeech(); });
  var main = document.querySelector('#main-content');
  var lastWord = visibleWord();
  if (main) new MutationObserver(function () {
    var word = visibleWord();
    if (!word || word !== lastWord) window.LexiAndroid.stopSpeech();
    lastWord = word;
  }).observe(main, {childList: true, subtree: true});
})();
