import {selectWord} from './selection.js';
import {readStore, updateStore, resetStore, storageAvailable} from './storage.js';
import {icon} from './icons.js';
import {dailySchedule, deviceTimezone, validUpdateTime} from './schedule.js';
import {answerMatches, withoutAnswer} from './recall.js';

const $ = (selector, root = document) => root.querySelector(selector);
const main = $('#main-content');
const onboarding = $('#onboarding-dialog');
const detail = $('#detail-dialog');
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const safeUrl = (value, contact = false) => {
  try {
    const url = new URL(value);
    return (contact ? ['https:', 'mailto:', 'tel:'] : ['https:']).includes(url.protocol) ? escape(url.href) : '#';
  } catch { return '#'; }
};

let catalog;
let preferences = readStore();
let today;
let dailyWord;
let currentWord;
let collectionDraft = new Set();
let toastTimer;
let observer;
let installPrompt;
let initialized = false;
let speaking = false;
let schedule;
let flipping = false;
let lastTouch;
let ignoreDoubleClickUntil = 0;
let revealPressAt = 0;

function isHidden(word) { return preferences.hiddenWords.includes(word.id); }
function motionReduced() { return preferences.reduceMotion || matchMedia('(prefers-reduced-motion: reduce)').matches; }

function scheduleFields(prefix) {
  const timezone = deviceTimezone(catalog?.timezone);
  return `<div class="schedule-fields"><label for="${prefix}-update-time"><span class="micro">A NEW WORD AT</span><input type="time" id="${prefix}-update-time" name="updateTime" required value="${preferences.updateTime}"></label><div class="schedule-timezone">${icon('clock')}<div><span class="micro">YOUR DEVICE TIMEZONE</span><strong>${escape(timezone.replaceAll('_',' '))}</strong><span>Follows your device when you travel.</span></div></div></div>`;
}

function rhythmSection() {
  return `<section class="settings-section"><div class="settings-section-heading"><div><h2>Your daily rhythm</h2><p>A small discovery, at a time that fits your day.</p></div>${icon('clock')}</div><form id="schedule-form">${scheduleFields('settings')}<div class="schedule-save"><p>Before your chosen time, yesterday’s word stays with you. Changing the time can recalculate the current word.</p><button type="submit" class="button button-primary">Save daily rhythm ${icon('check')}</button></div><p id="schedule-feedback" class="schedule-feedback" role="status"></p></form><p class="privacy-note">When the browser is closed, your next visit applies the schedule. No background notification is sent.</p></section>`;
}

function nextWordLabel() {
  if (!schedule) return '';
  const tomorrow = schedule.date === today;
  return `Next word ${tomorrow ? 'tomorrow' : 'today'} at ${preferences.updateTime}`;
}

function renderRecall(word, archived) {
  const collection = collectionFor(word);
  const clue = withoutAnswer(word.shortDefinition, word.word);
  return `<section class="hero recall-hero page-width" aria-labelledby="recall-title"><div class="hero-topline"><span class="eyebrow"><span class="live-dot"></span>MAKE IT A MEMORY</span><time datetime="${today}">${formatDate(today,{day:'numeric',month:'long'})}</time></div><div class="word-stage recall-stage" data-flip-surface="back"><div class="collection-tag">${icon(collection.icon)}<span>${escape(collection.name)}</span><span class="word-class">${escape(word.partOfSpeech)}</span></div><div class="recall-top"><span class="micro">THE OTHER SIDE / RECALL PRACTICE</span><span class="recall-orbit" aria-hidden="true">${icon('flip')}</span></div><h1 id="recall-title" tabindex="-1">Let it<br><em>come back.</em></h1><p class="recall-clue">${escape(clue)}</p><form id="recall-form" class="recall-form"><label for="recall-answer">What’s the English word?</label><div class="recall-input-row"><input id="recall-answer" name="answer" type="text" placeholder="Type it from memory…" autocomplete="off" autocorrect="off" autocapitalize="none" spellcheck="false" required maxlength="200" aria-describedby="recall-feedback"><button type="submit" class="button button-primary">Check my word ${icon('arrow')}</button></div><p id="recall-feedback" class="recall-feedback" role="status" aria-live="polite">A correct answer turns the card back. Capital letters don’t matter.</p></form><div class="recall-alternative"><span class="micro">OR DOUBLE-TAP THIS CARD</span><button class="recall-double-button text-link" data-action="reveal-twice">${icon('flip')}<span>Press twice to reveal</span></button></div><p class="recall-memory-note">${icon('bookmark')}${storageAvailable ? 'This side is remembered, even after you close your browser.' : 'Storage is unavailable. This side is remembered for this visit only.'}</p></div><div class="hero-bottom"><a class="text-link" href="#${archived ? 'history' : 'settings'}">${archived ? 'Back to your history' : 'Your daily rhythm'} ${icon('arrowUp')}</a><span class="next-word-label micro">${escape(nextWordLabel())}</span></div></section>`;
}

async function flipCard(hidden, successMessage) {
  if (!currentWord || flipping) return;
  const word = currentWord;
  const route = location.hash;
  flipping = true;
  revealPressAt = 0;
  preferences = updateStore({hiddenWords: hidden ? [...new Set([...preferences.hiddenWords,word.id])] : preferences.hiddenWords.filter(id => id !== word.id)});
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  speaking = false;
  if (detail.open) detail.close();
  try {
    const oldFace = $('.word-stage');
    if (oldFace && !motionReduced() && oldFace.animate) {
      await oldFace.animate([{transform:'perspective(1400px) rotateX(0deg)',opacity:1},{transform:'perspective(1400px) rotateX(-85deg)',opacity:.1}],{duration:180,easing:'ease-in',fill:'forwards'}).finished;
    }
    if (currentWord?.id !== word.id || location.hash !== route) return;
    renderApp({scroll:false});
    const newFace = $('.word-stage');
    if (newFace && !motionReduced() && newFace.animate) {
      // The incoming visual may finish while the new face is already usable.
      newFace.animate([{transform:'perspective(1400px) rotateX(85deg)',opacity:.1},{transform:'perspective(1400px) rotateX(0deg)',opacity:1}],{duration:260,easing:'cubic-bezier(.16,1,.3,1)'});
    }
    if (hidden) $('#recall-answer')?.focus({preventScroll:true});
    else $('#daily-word')?.focus({preventScroll:true});
    toast(!storageAvailable ? 'Browser storage is unavailable. This card position lasts for this visit only.' : successMessage || (hidden ? 'Word hidden. Come back to it from memory.' : 'A familiar word, back in your world.'));
  } catch (error) {
    if (currentWord?.id === word.id && location.hash === route) renderApp({scroll:false});
  } finally { flipping = false; }
}

document.querySelectorAll('[data-icon]').forEach(element => element.innerHTML = icon(element.dataset.icon));

function toast(message) {
  clearTimeout(toastTimer);
  const element = $('#toast');
  element.textContent = message;
  element.hidden = false;
  toastTimer = setTimeout(() => { element.hidden = true; }, 4500);
}

function collectionFor(word) {
  return catalog.collections.find(collection => collection.id === word.collectionId);
}

function formatDate(day, options = {month: 'long', day: 'numeric', year: 'numeric'}) {
  return new Intl.DateTimeFormat('en-GB', {timeZone: 'UTC', ...options}).format(new Date(`${day}T12:00:00Z`));
}

function updateHeader() {
  const previousCount = $('#saved-count').textContent;
  $('#saved-count').textContent = preferences.saved.length;
  if (previousCount !== String(preferences.saved.length) && !motionReduced()) {
    $('#saved-count').animate?.([{transform:'scale(1)'},{transform:'scale(1.22)'},{transform:'scale(1)'}],{duration:300});
  }
  $('.saved-link').setAttribute('aria-label', `Saved words, ${preferences.saved.length} saved`);
  const route = readRoute().page;
  document.querySelectorAll('[data-nav]').forEach(link => {
    const active = link.dataset.nav === (route === 'word' ? 'home' : route);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

function applyAppearance() {
  document.documentElement.dataset.theme = preferences.theme;
  document.documentElement.classList.toggle('reduce-motion', preferences.reduceMotion);
  $('meta[name="theme-color"]').content = {noir: '#111216', studio: '#E6E5DD', experimental: '#0A0B1D'}[preferences.theme];
}

function calculateDaily() {
  schedule = dailySchedule(deviceTimezone(catalog.timezone), preferences.updateTime);
  today = schedule.calendarDate;
  const selected = preferences.interests.length ? preferences.interests : catalog.collections.map(collection => collection.id);
  dailyWord = selectWord(catalog.collections, catalog.words, selected, schedule.date);
}

function recordView(word) {
  if (!preferences.onboarded) return;
  if (!preferences.history.some(item => item.id === word.id && item.date === today)) {
    preferences = updateStore({history: [...preferences.history, {id: word.id, date: today}]});
  }
}

function readRoute() {
  let hash;
  try { hash = decodeURIComponent(location.hash.slice(1)); }
  catch { return {page: 'home'}; }
  if (hash.startsWith('word/')) return {page: 'word', id: hash.slice(5)};
  return {page: ['home', 'collections', 'history', 'saved', 'settings'].includes(hash) ? hash : 'home'};
}

function navigate(page) {
  if (location.hash === `#${page}`) renderApp();
  else location.hash = page;
}

function saveButton(word, extraClass = '') {
  const saved = preferences.saved.includes(word.id);
  return `<button class="button button-save ${extraClass} ${saved ? 'is-saved' : ''}" data-action="save" data-word="${escape(word.id)}" aria-pressed="${saved}">${icon('bookmark')}<span>${saved ? 'Word saved' : 'Save word'}</span></button>`;
}

function renderHome(word, archived = false) {
  if (isHidden(word)) return renderRecall(word, archived);
  const collection = collectionFor(word);
  const synonyms = word.synonyms || [];
  const related = word.relatedWords || [];
  const number = String(catalog.words.findIndex(item => item.id === word.id) + 1).padStart(3, '0');
  const categoryIndex = String(catalog.collections.indexOf(collection) + 1).padStart(2, '0');
  return `
    <section class="hero page-width" aria-labelledby="daily-word">
      <div class="hero-topline"><div class="eyebrow"><span class="live-dot"></span>${archived ? 'A WORD WORTH REVISITING' : 'WORD OF THE DAY'}</div><time datetime="${today}">${formatDate(today, {weekday: 'long', day: 'numeric', month: 'long'})}<span class="date-year"> / ${today.slice(0, 4)}</span></time></div>
      <div class="word-stage" data-flip-surface="front">
        <div class="collection-tag">${icon(collection.icon)}<span>${escape(collection.name)}</span><span class="collection-index">${categoryIndex} / ${String(catalog.collections.length).padStart(2, '0')}</span></div>
        <div class="orbit-art" aria-hidden="true"><img src="/static/assets/orbit.svg" alt=""></div>
        <div class="studio-art" aria-hidden="true"><i></i><i></i><i></i></div>
        <div class="word-wrap"><h1 id="daily-word" class="hero-word" tabindex="-1">${escape(word.word)}<span class="word-period">.</span></h1></div>
        <div class="word-under"><div class="pronunciation"><button class="listen-button" data-action="pronounce" aria-label="Listen to ${escape(word.word)}">${icon('volume')}</button><span class="ipa">${escape(word.ipa)}</span><span class="word-class">${escape(word.partOfSpeech)}</span></div><div class="word-tools">${saveButton(word)}<button class="icon-button share-button" data-action="share" aria-label="Share ${escape(word.word)}">${icon('share')}</button></div></div>
        <div class="card-practice-bar"><span class="micro">DOUBLE-TAP THE WORD TO TURN IT OVER</span><button class="text-link" data-action="hide-word">Test my memory ${icon('flip')}</button></div>
      </div>
      <div class="hero-meaning"><div class="meaning-caption"><span class="micro">THE MEANING</span><span class="small-index">/ ${number}</span></div><div class="meaning-content"><p class="short-definition">${escape(word.shortDefinition)}</p><div class="synonym-pills"><span class="micro muted">CLOSE IN MEANING</span>${synonyms.map((item, index) => `<button class="synonym" data-action="synonym" data-index="${index}">${escape(item.word)} ${icon('arrowUp')}</button>`).join('')}</div><p class="hero-example">“${escape(word.examples[0])}”</p></div></div>
      <div class="hero-bottom"><span class="micro muted">ONE DAY. ONE WORD.<br><span class="hero-motto">A LITTLE MORE KNOWLEDGE.</span></span><span class="next-word-label micro">${escape(nextWordLabel())}</span><button class="scroll-discover" data-action="explore"><span>SCROLL TO EXPLORE</span><span class="scroll-circle">${icon('down')}</span></button></div>
    </section>
    <section id="beyond-word" class="beyond-section" aria-labelledby="beyond-title"><div class="page-width">
      <div class="section-label reveal"><span class="eyebrow">BEYOND THE WORD</span><span class="micro">/ 01</span></div>
      <div class="beyond-intro reveal"><h2 id="beyond-title">More than<br>a <em>definition.</em></h2><p>Because knowing a word is one thing.<br>Making it part of your world is another.</p></div>
      <div class="explanation-grid">
        <article class="definition-block reveal"><div class="content-label"><span>01</span><h3>The bigger picture</h3></div><p>${escape(word.fullDefinition)}</p>${word.source ? `<a class="reference-link" href="${safeUrl(word.source.url)}" target="_blank" rel="noopener noreferrer">${escape(word.source.label)} ${icon('arrowUp')}</a>` : ''}</article>
        <article class="simple-block reveal"><span class="micro">IN OTHER WORDS</span><span class="simple-star" aria-hidden="true">${icon('asterisk')}</span><p>${escape(word.simpleExplanation)}</p><span class="micro muted">SIMPLE ENGLISH. SAME IDEA.</span></article>
      </div>
      <div class="examples-section reveal"><div class="content-label"><span>02</span><h3>Out in the world</h3><span class="content-label-note">ONE WORD, DIFFERENT CONTEXTS</span></div><div class="example-grid">${word.examples.map((example, index) => `<article class="example-item"><span class="micro muted">${String(index + 1).padStart(2, '0')} / IN CONTEXT</span><p>“${escape(example)}”</p></article>`).join('')}</div></div>
      <div class="nuance-section reveal"><div class="content-label"><span>03</span><h3>Close, but a little different</h3></div><div class="nuance-list">${synonyms.length ? synonyms.map((item, index) => `<button class="nuance-row" data-action="synonym" data-index="${index}"><span class="nuance-word">${escape(item.word)}</span><span>${escape(item.definition || 'Open to see available information.')}</span>${icon('arrowUp')}</button>`).join('') : '<p class="muted">No synonyms have been added to this entry yet.</p>'}</div></div>
      <div class="related-layout reveal"><div><div class="content-label"><span>04</span><h3>Follow the thread</h3></div><div class="related-words">${related.length ? related.map((item, index) => `<button class="related-word" data-action="related" data-index="${index}">${escape(item.word)} ${icon('arrowUp')}</button>`).join('') : '<p class="muted">More connections will be added as this collection grows.</p>'}</div></div>${word.usageNote ? `<aside class="usage-note">${icon('info')}<div><span class="micro">A NOTE TO REMEMBER</span><p>${escape(word.usageNote)}</p></div></aside>` : ''}</div>
      <div class="save-ritual reveal"><div><span class="eyebrow">MAKE IT PART OF YOUR WORLD</span><h3>A good word is worth keeping<span class="accent">.</span></h3></div>${saveButton(word)}</div>
    </div></section>`;
}

function collectionCard(collection, index, selected, context) {
  const count = catalog.words.filter(word => word.collectionId === collection.id).length;
  return `<label class="collection-card"><input type="checkbox" name="${context}" value="${escape(collection.id)}" ${selected ? 'checked' : ''}><span class="collection-card-top"><span class="collection-number">${String(index + 1).padStart(2, '0')}</span><span class="selection-check">${icon('check')}</span></span><span class="collection-visual">${icon(collection.icon)}</span><span class="collection-card-name">${escape(collection.name)}</span><span class="collection-card-description">${escape(collection.description)}</span><span class="collection-card-footer"><span>${String(count).padStart(2, '0')} WORDS TO DISCOVER</span><span class="selection-state"><span class="unselected-label">Select collection</span><span class="selected-label">Selected</span></span></span></label>`;
}

function renderCollections() {
  collectionDraft = new Set(preferences.interests);
  return `<section class="interior-page page-width"><div class="section-label"><span class="eyebrow">YOUR COLLECTIONS</span><span class="micro">FOLLOW YOUR CURIOSITY</span></div><div class="page-heading"><h1 tabindex="-1">A world of words.<br><span class="accent">Built around you.</span></h1><p>Choose the things that move you.<br>We’ll find the words to match.</p></div><div class="collections-grid">${catalog.collections.map((collection, index) => collectionCard(collection, index, collectionDraft.has(collection.id), 'interests')).join('')}</div><div class="collection-actions"><p id="selection-summary" aria-live="polite">${collectionDraft.size} ${collectionDraft.size === 1 ? 'collection' : 'collections'} selected. A new perspective, every day.</p><button class="button button-primary" data-action="apply-collections" ${collectionDraft.size ? '' : 'disabled'}>Update my daily word ${icon('arrow')}</button></div><p class="privacy-note">Select at least one collection. Your interests stay in this browser. Changing them recalculates today’s word.</p></section>`;
}

function listRecords(page, query = '') {
  const needle = query.trim().toLocaleLowerCase();
  let records = page === 'saved'
    ? preferences.saved.slice().reverse().map(id => ({id}))
    : preferences.history.filter(item => item.date <= today).slice().reverse().sort((a, b) => b.date.localeCompare(a.date));
  records = records.map(record => ({...record, word: catalog.words.find(word => word.id === record.id)}))
    .filter(record => record.word && (!needle || `${record.word.word} ${collectionFor(record.word).name} ${record.word.shortDefinition}`.toLocaleLowerCase().includes(needle)));
  if (!records.length) {
    if (needle) return `<div class="empty-state"><span class="empty-symbol">${icon('search')}</span><h2>No words found.</h2><p>Try another word or collection name.</p><button class="button button-outline" data-action="clear-search">Clear search ${icon('close')}</button></div>`;
    return `<div class="empty-state"><span class="empty-symbol">${icon(page === 'saved' ? 'bookmark' : 'history')}</span><h2>${page === 'saved' ? 'Keep the words that stay with you.' : 'Your story starts with a word.'}</h2><p>${page === 'saved' ? 'Tap “Save word” on a word you love. You’ll find it right here.' : 'Words appear here after you view them. Your future discoveries stay a surprise.'}</p><a class="button button-primary" href="#home">Discover today’s word ${icon('arrow')}</a></div>`;
  }
  let lastDate;
  return records.map(({word, date}) => {
    let heading = '';
    if (page === 'history' && date !== lastDate) {
      lastDate = date;
      heading = `<h2 class="history-date micro">${date === today ? 'TODAY · ' : ''}${formatDate(date)}</h2>`;
    }
    return `${heading}<article class="word-card"><a class="word-card-main" href="#word/${escape(word.id)}"><span class="micro muted">${escape(collectionFor(word).name)}</span><h${page === 'history' ? '3' : '2'}>${isHidden(word) ? 'A word to recall' : escape(word.word)}<span class="list-word-class">${escape(word.partOfSpeech)}</span></h${page === 'history' ? '3' : '2'}><p>${escape(isHidden(word) ? withoutAnswer(word.shortDefinition,word.word) : word.shortDefinition)}</p></a><div class="word-card-actions">${page === 'saved' ? `<button class="icon-button is-saved" data-action="save" data-word="${escape(word.id)}" aria-label="Remove ${isHidden(word) ? 'this word' : escape(word.word)} from Saved">${icon('bookmark')}</button>` : ''}<a class="icon-button" href="#word/${escape(word.id)}" aria-label="${isHidden(word) ? 'Practice this word' : 'Read ' + escape(word.word)}">${icon('arrowUp')}</a></div></article>`;
  }).join('');
}

function renderList(page) {
  const saved = page === 'saved';
  const count = saved ? preferences.saved.length : new Set(preferences.history.filter(item => item.date <= today).map(item => item.id)).size;
  return `<section class="interior-page page-width"><div class="section-label"><span class="eyebrow">${saved ? 'YOUR PERSONAL WORDSHELF' : 'YOUR VOCABULARY JOURNEY'}</span><span class="micro">${String(count).padStart(2, '0')} ${count === 1 ? 'WORD' : 'WORDS'} ${saved ? 'SAVED' : 'ENCOUNTERED'}</span></div><div class="page-heading"><h1 tabindex="-1">${saved ? 'Some words<br><span class="accent">are worth keeping.</span>' : 'A little wiser.<br><span class="accent">One day at a time.</span>'}</h1><p>${saved ? 'Your favorites, all in one place.<br>Come back whenever you need them.' : 'Every word you’ve actually explored.<br>A small record of a growing world.'}</p></div><label class="search-field">${icon('search')}<span class="sr-only">Search ${page} words</span><input type="search" id="word-search" placeholder="Search your ${page === 'saved' ? 'saved words' : 'history'}…" autocomplete="off"></label><div id="word-list" class="word-list">${listRecords(page)}</div><p class="privacy-note">Your words are stored in this browser. They don’t sync between devices.</p></section>`;
}

function renderSettings() {
  return `<section class="interior-page settings-page page-width"><div class="section-label"><span class="eyebrow">MAKE YOURSELF AT HOME</span><span class="micro">SETTINGS</span></div><div class="page-heading"><h1 tabindex="-1">Your world.<br><span class="accent">Your atmosphere.</span></h1><p>A few thoughtful details.<br>Just the way you like them.</p></div><section class="settings-section"><div class="settings-section-heading"><h2>Choose your atmosphere</h2><p>Same word. A different point of view.</p></div><div class="theme-grid">${[['noir', '01', 'Noir', 'Quiet confidence. After dark.'], ['studio', '02', 'Studio', 'Warm light. A clear mind.'], ['experimental', '03', 'Experimental', 'A little outside the ordinary.']].map(([id, number, name, description]) => `<button class="theme-card" data-theme-choice="${id}" aria-pressed="${preferences.theme === id}"><span class="theme-preview theme-preview-${id}"><span class="micro">LEXI / ${number}</span><span class="theme-preview-word">Aa<span>.</span></span><span class="theme-preview-line"></span></span><span class="theme-name">${name}<span class="theme-check">${icon('check')}</span></span><span class="theme-description">${description}</span></button>`).join('')}</div></section><section class="settings-section"><div class="settings-row"><div><h2>A gentler pace</h2><p>Reduce animations and decorative movement.<br>Your device’s reduced-motion setting is always respected.</p></div><label class="switch"><input id="motion-toggle" type="checkbox" role="switch" ${preferences.reduceMotion ? 'checked' : ''}><span class="switch-track"></span><span class="sr-only">Reduce motion</span></label></div><div class="settings-row"><div><h2>Follow your interests</h2><p>${preferences.interests.length} collections shape your daily discoveries.</p></div><a class="text-link" href="#collections">Edit collections ${icon('arrowUp')}</a></div><div class="settings-row"><div><h2>Make it a memory</h2><p>Double-tap a word to turn it over. Bring it back with the correct spelling, or another double-tap.<br>Your card position is saved in this browser.</p></div><a class="text-link" href="#home">Practice your word ${icon('flip')}</a></div></section>${rhythmSection()}<section class="settings-section"><div class="settings-row"><div><h2>A little closer, every day</h2><p>Install LEXI from your browser menu: “Add to Home Screen” or “Install app”.<br>After your first online visit, cached words are available offline.</p></div><button id="install-button" class="button button-outline" data-action="install" ${installPrompt ? '' : 'hidden'}>Install LEXI ${icon('download')}</button></div></section><section class="settings-section local-data-section"><div><span class="micro">YOUR BROWSER, YOUR DATA</span><h2>Small rituals. Local memories.</h2><p>Interests, saved words, and history stay on this device. Export a personal backup before clearing browser data.</p></div><div class="data-actions"><button class="button button-outline" data-action="export">Export my data ${icon('download')}</button><button class="text-link danger-link" data-action="reset">Reset local data ${icon('trash')}</button></div></section></section>`;
}

function renderFooter() {
  const site = catalog.site;
  $('#site-footer').innerHTML = `<div class="page-width"><div class="footer-top reveal"><div><span class="eyebrow">A SMALL RITUAL. AN EXPANDING WORLD.</span><h2>${escape(site.tagline)}</h2><p>${escape(site.description)}</p></div><div class="footer-contacts">${(site.contacts || []).map(contact => `<a href="${safeUrl(contact.url, true)}" ${contact.url.startsWith('https:') ? 'target="_blank" rel="noopener noreferrer"' : ''}><span>${icon(contact.icon)}<span><span class="micro">${escape(contact.label)}</span><span>${escape(contact.text)}</span></span></span>${icon('arrowUp')}</a>`).join('')}</div></div><a class="footer-wordmark reveal" href="#home" aria-label="LEXI Home">LEXI<span>${icon('asterisk')}</span></a><div class="footer-bottom"><span>© ${today.slice(0, 4)} LEXI. A little more knowledge.</span><span>MADE FOR CURIOUS MINDS.</span><a href="#settings">Your preferences ${icon('arrowUp')}</a></div></div>`;
}

function renderApp({scroll = true} = {}) {
  if (!catalog) return;
  const route = readRoute();
  currentWord = null;
  if (route.page === 'home' || route.page === 'word') {
    const word = route.page === 'word' ? catalog.words.find(item => item.id === route.id) : dailyWord;
    if (word) {
      currentWord = word;
      recordView(word);
      main.innerHTML = renderHome(word, route.page === 'word');
      document.title = isHidden(word) ? 'Recall practice — LEXI' : `${word.word} — LEXI`;
    } else {
      main.innerHTML = `<section class="interior-page page-width empty-state"><h1 tabindex="-1">That word isn’t here yet.</h1><p>The link may be outdated, or the entry may have been removed.</p><a class="button button-primary" href="#home">Back to today ${icon('arrow')}</a></section>`;
    }
  } else {
    main.innerHTML = route.page === 'collections' ? renderCollections() : route.page === 'settings' ? renderSettings() : renderList(route.page);
    document.title = `${route.page[0].toUpperCase() + route.page.slice(1)} — LEXI`;
  }
  updateHeader();
  main.classList.remove('page-enter');
  requestAnimationFrame(() => main.classList.add('page-enter'));
  observeReveals();
  requestAnimationFrame(fitWord);
  document.fonts.ready.then(fitWord);
  if (scroll) {
    window.scrollTo({top: 0, behavior: 'instant'});
    if (initialized && !onboarding.open) $('h1', main)?.focus({preventScroll: true});
  }
}

function fitWord() {
  const heading = $('.hero-word');
  if (!heading) return;
  heading.classList.remove('wrap-word');
  heading.style.fontSize = '';
  const width = heading.parentElement.clientWidth;
  const range = document.createRange();
  range.selectNodeContents(heading);
  const textWidth = range.getBoundingClientRect().width;
  const size = parseFloat(getComputedStyle(heading).fontSize);
  if (textWidth > width) {
    const fitted = size * (width - 4) / textWidth;
    if (fitted >= 38) heading.style.fontSize = `${fitted}px`;
    else { heading.classList.add('wrap-word'); heading.style.fontSize = '38px'; }
  }
}

function observeReveals() {
  observer?.disconnect();
  if (!('IntersectionObserver' in window)) return;
  observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); }
  }), {threshold: 0.08});
  document.querySelectorAll('.reveal').forEach((element, index) => {
    element.dataset.revealStyle = ['rise','slide','scale'][index % 3];
    element.classList.add('will-reveal');
    observer.observe(element);
  });
}

function showOnboarding() {
  $('#onboarding-schedule').innerHTML = scheduleFields('onboarding');
  $('#onboarding-collections').innerHTML = catalog.collections.map((collection, index) => collectionCard(collection, index, preferences.interests.includes(collection.id), 'onboarding')).join('');
  $('#begin-button').disabled = !preferences.interests.length;
  if (!onboarding.open) onboarding.showModal();
}

function openDetail(title, content) {
  detail.innerHTML = `<button class="icon-button dialog-close" data-action="close-dialog" aria-label="Close dialog">${icon('close')}</button><span class="eyebrow">A LITTLE MORE CONTEXT</span><h2 id="detail-title">${escape(title)}</h2>${content}`;
  if (!detail.open) detail.showModal();
}

function toggleSave(id) {
  const word = catalog.words.find(item => item.id === id);
  if (!word) return;
  const had = preferences.saved.includes(id);
  preferences = updateStore({saved: had ? preferences.saved.filter(item => item !== id) : [...preferences.saved, id]});
  updateHeader();
  const page = readRoute().page;
  if (page === 'saved') {
    const query = $('#word-search')?.value || '';
    $('#word-list').innerHTML = listRecords(page, query);
    $('.section-label .micro', main).textContent = `${String(preferences.saved.length).padStart(2, '0')} ${preferences.saved.length === 1 ? 'WORD' : 'WORDS'} SAVED`;
    $('#word-search')?.focus({preventScroll: true});
  } else {
    document.querySelectorAll('[data-action="save"]').forEach(button => {
      if (button.dataset.word !== id) return;
      button.setAttribute('aria-pressed', String(!had));
      button.classList.toggle('is-saved', !had);
      const label = $('span', button);
      if (label) label.textContent = had ? 'Save word' : 'Word saved';
      button.classList.remove('save-pop');
      requestAnimationFrame(() => button.classList.add('save-pop'));
    });
  }
  const label = isHidden(word) ? 'Word' : word.word;
  toast(had ? `${label} removed from Saved.` : `${label} saved. A little knowledge, kept.`);
}

function pronounce() {
  if (!currentWord || isHidden(currentWord)) return;
  if (!('speechSynthesis' in window)) { toast('Pronunciation is not supported in this browser. The IPA transcription is shown beside the button.'); return; }
  if (speaking) { speechSynthesis.cancel(); speaking = false; return; }
  const utterance = new SpeechSynthesisUtterance(currentWord.word);
  const voice = speechSynthesis.getVoices().find(item => item.lang.toLowerCase().startsWith('en-gb')) || speechSynthesis.getVoices().find(item => item.lang.toLowerCase().startsWith('en'));
  if (voice) utterance.voice = voice;
  utterance.lang = 'en-GB';
  utterance.rate = 0.8;
  utterance.onstart = () => { speaking = true; $('.listen-button')?.classList.add('is-speaking'); };
  utterance.onend = () => { speaking = false; $('.listen-button')?.classList.remove('is-speaking'); };
  utterance.onerror = event => {
    speaking = false;
    $('.listen-button')?.classList.remove('is-speaking');
    if (!['canceled', 'interrupted'].includes(event.error)) toast('No English speech voice is available. Check your browser or device speech settings; you can also read the IPA.');
  };
  speechSynthesis.speak(utterance);
}

async function shareWord() {
  if (!currentWord || isHidden(currentWord)) return;
  const url = `${location.origin}/#word/${encodeURIComponent(currentWord.id)}`;
  const payload = {title: `${currentWord.word} — LEXI`, text: `${currentWord.word}: ${currentWord.shortDefinition}`, url};
  try {
    if (navigator.share && (!navigator.canShare || navigator.canShare(payload))) { await navigator.share(payload); return; }
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(url); toast('Word link copied. Share a little knowledge.'); return; }
  } catch (error) { if (error.name === 'AbortError') return; }
  openDetail('Pass a word along.', `<p>Copy this link to share the word:</p><label class="share-url-label">Word link<input class="share-url" type="text" readonly value="${escape(url)}"></label>`);
  $('.share-url', detail).select();
}

document.addEventListener('click', async event => {
  const themeButton = event.target.closest('[data-theme-choice]');
  if (themeButton) {
    preferences = updateStore({theme: themeButton.dataset.themeChoice});
    applyAppearance();
    document.querySelectorAll('[data-theme-choice]').forEach(button => button.setAttribute('aria-pressed', String(button === themeButton)));
    toast(`${preferences.theme[0].toUpperCase() + preferences.theme.slice(1)} atmosphere. Same daily word.`);
    return;
  }
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  switch (button.dataset.action) {
    case 'hide-word': await flipCard(true); break;
    case 'reveal-twice': {
      if (!currentWord || !isHidden(currentWord)) break;
      const now = performance.now();
      if (revealPressAt > 0 && now - revealPressAt < 1800) await flipCard(false);
      else {
        revealPressAt = now;
        $('span',button).textContent = 'Once more to reveal';
        setTimeout(() => {
          if (revealPressAt === now) {
            revealPressAt = 0;
            const label = $('[data-action="reveal-twice"] span');
            if (label) label.textContent = 'Press twice to reveal';
          }
        },1800);
      }
      break;
    }
    case 'save': toggleSave(button.dataset.word); break;
    case 'pronounce': pronounce(); break;
    case 'share': await shareWord(); break;
    case 'explore': $('#beyond-word')?.scrollIntoView({behavior: preferences.reduceMotion || matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'}); break;
    case 'synonym':
    case 'related': {
      const item = (button.dataset.action === 'synonym' ? currentWord?.synonyms : currentWord?.relatedWords)?.[Number(button.dataset.index)];
      if (item) openDetail(item.word, `<span class="dialog-type micro">${button.dataset.action === 'synonym' ? 'CLOSE IN MEANING' : 'RELATED VOCABULARY'}</span><p>${escape(item.definition || 'No definition is included for this word yet.')}</p><p class="dialog-note">A connection to <strong>${escape(currentWord.word)}</strong>. Meanings can change with context.</p>`);
      break;
    }
    case 'close-dialog': detail.close(); break;
    case 'apply-collections':
      if (!collectionDraft.size) { toast('Choose at least one collection.'); break; }
      preferences = updateStore({interests: [...collectionDraft]});
      calculateDaily();
      navigate('home');
      toast('Your daily discovery now follows your interests.');
      break;
    case 'clear-search': $('#word-search').value = ''; $('#word-list').innerHTML = listRecords(readRoute().page); $('#word-search').focus(); break;
    case 'reset':
      openDetail('A fresh start?', `<p>This clears your interests, saved words, history, and appearance settings in this browser. You can export your data first in Settings.</p><p class="dialog-note">This action cannot be undone in the app.</p><div class="dialog-actions"><button class="button button-outline" data-action="close-dialog">Keep my data</button><button class="button button-primary" data-action="confirm-reset">Reset this browser ${icon('arrow')}</button></div>`);
      break;
    case 'confirm-reset':
      preferences = resetStore();
      applyAppearance();
      detail.close();
      calculateDaily();
      navigate('home');
      showOnboarding();
      toast('A fresh start. Follow your curiosity.');
      break;
    case 'export': {
      const blob = new Blob([JSON.stringify({app: 'LEXI', exportedAt: new Date().toISOString(), preferences: readStore()}, null, 2)], {type: 'application/json'});
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `LEXI-my-data-${today}.json`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast('Your browser data has been exported.');
      break;
    }
    case 'install':
      if (installPrompt) { await installPrompt.prompt(); await installPrompt.userChoice; installPrompt = null; button.hidden = true; }
      break;
    case 'retry': await initialize(); break;
  }
});

document.addEventListener('change', event => {
  const input = event.target;
  if (input.name === 'onboarding') {
    $('#begin-button').disabled = !onboarding.querySelectorAll('input[name="onboarding"]:checked').length || !validUpdateTime($('#onboarding-update-time').value);
  } else if (input.name === 'interests') {
    if (input.checked) collectionDraft.add(input.value); else collectionDraft.delete(input.value);
    $('#selection-summary').textContent = collectionDraft.size ? `${collectionDraft.size} ${collectionDraft.size === 1 ? 'collection' : 'collections'} selected. A new perspective, every day.` : 'Choose at least one collection to continue.';
    $('[data-action="apply-collections"]').disabled = !collectionDraft.size;
  } else if (input.id === 'motion-toggle') {
    preferences = updateStore({reduceMotion: input.checked});
    applyAppearance();
    toast(input.checked ? 'A gentler pace. Animations reduced.' : 'Animations follow your device preference.');
  }
});

document.addEventListener('input', event => {
  if (event.target.id === 'word-search') $('#word-list').innerHTML = listRecords(readRoute().page, event.target.value);
  if (event.target.id === 'onboarding-update-time') $('#begin-button').disabled = !onboarding.querySelectorAll('input[name="onboarding"]:checked').length || !validUpdateTime(event.target.value);
});

document.addEventListener('submit', async event => {
  if (event.target.id === 'recall-form') {
    event.preventDefault();
    if (!currentWord || !isHidden(currentWord) || flipping) return;
    const answer = $('#recall-answer');
    if (answerMatches(answer.value,currentWord.word)) await flipCard(false,'You recalled it. That word is becoming yours.');
    else {
      answer.setAttribute('aria-invalid','true');
      $('#recall-feedback').textContent = 'Not quite. Check the spelling and try again, or double-tap the card to reveal.';
      answer.focus();
      if (!motionReduced()) answer.animate?.([{transform:'translateX(0)'},{transform:'translateX(-5px)'},{transform:'translateX(5px)'},{transform:'translateX(0)'}],{duration:220});
    }
  } else if (event.target.id === 'schedule-form') {
    event.preventDefault();
    const input = $('#settings-update-time');
    if (!validUpdateTime(input.value)) { input.reportValidity(); return; }
    preferences = updateStore({updateTime:input.value});
    calculateDaily();
    renderApp({scroll:false});
    $('#schedule-feedback').textContent = `${nextWordLabel()} · ${schedule.timezone.replaceAll('_',' ')}`;
    $('#schedule-form button[type="submit"]').focus({preventScroll:true});
    toast(storageAvailable ? `Daily rhythm saved: ${preferences.updateTime}, in your device’s timezone.` : 'Browser storage is unavailable. This schedule lasts for this visit only.');
  }
});

function surfaceFrom(event) {
  if (event.target.closest('button,a,input,select,textarea,label,form')) return null;
  return event.target.closest('[data-flip-surface]');
}

document.addEventListener('dblclick', event => {
  if (performance.now() < ignoreDoubleClickUntil || !surfaceFrom(event)) return;
  event.preventDefault();
  if (currentWord) flipCard(!isHidden(currentWord));
});

document.addEventListener('pointerup', event => {
  if (event.pointerType !== 'touch' || !event.isPrimary) return;
  const surface = surfaceFrom(event);
  if (!surface || !currentWord) { lastTouch = null; return; }
  const now = performance.now();
  const tap = {id:currentWord.id, face:surface.dataset.flipSurface, at:now, x:event.clientX, y:event.clientY};
  if (lastTouch && lastTouch.id === tap.id && lastTouch.face === tap.face && now-lastTouch.at <= 380 && Math.hypot(tap.x-lastTouch.x,tap.y-lastTouch.y)<30) {
    event.preventDefault();
    ignoreDoubleClickUntil = now + 650;
    lastTouch = null;
    flipCard(!isHidden(currentWord));
  } else lastTouch = tap;
});

$('#begin-button').addEventListener('click', () => {
  const selected = [...onboarding.querySelectorAll('input[name="onboarding"]:checked')].map(input => input.value);
  if (!selected.length) return;
  const timeInput = $('#onboarding-update-time');
  if (!validUpdateTime(timeInput.value)) { timeInput.reportValidity(); return; }
  preferences = updateStore({interests: selected, updateTime:timeInput.value, onboarded: true});
  calculateDaily();
  onboarding.close();
  renderApp();
  initialized = true;
  toast('Welcome to your daily ritual. A little more knowledge starts here.');
});

onboarding.addEventListener('cancel', event => event.preventDefault());
detail.addEventListener('click', event => {
  if (event.target === detail) {
    const bounds = detail.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) detail.close();
  }
});

window.addEventListener('hashchange', () => {
  if (detail.open) detail.close();
  if ('speechSynthesis' in window) speechSynthesis.cancel();
  speaking = false;
  renderApp();
});
window.addEventListener('resize', fitWord);
window.addEventListener('storage', event => {
  if (event.key !== 'lexi:v1' && event.key !== null) return;
  preferences = readStore();
  if (!catalog) return;
  sanitizePreferences();
  applyAppearance();
  calculateDaily();
  renderApp({scroll: false});
  if (!preferences.onboarded) showOnboarding();
  else if (onboarding.open) onboarding.close();
});

function updateNetwork() {
  $('#offline-banner').hidden = navigator.onLine;
}
window.addEventListener('online', () => { updateNetwork(); toast('Back online. Your curiosity never stopped.'); });
window.addEventListener('offline', () => { updateNetwork(); toast('Offline. Cached vocabulary is still available.'); });
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault(); installPrompt = event;
  if ($('#install-button')) $('#install-button').hidden = false;
});

function checkDay() {
  if (!catalog) return;
  const latest = dailySchedule(deviceTimezone(catalog.timezone),preferences.updateTime);
  if (latest.date === schedule.date && latest.calendarDate === today && latest.timezone === schedule.timezone) return;
  const previousWord = dailyWord?.id;
  calculateDaily();
  renderFooter();
  renderApp({scroll: false});
  if (dailyWord?.id !== previousWord) toast('A new day. A new word to make your own.');
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkDay(); });
setInterval(checkDay, 30000);

function sanitizePreferences() {
  const collectionIds = new Set(catalog.collections.map(item => item.id));
  const wordIds = new Set(catalog.words.map(item => item.id));
  const interests = preferences.interests.filter(id => collectionIds.has(id));
  preferences = updateStore({
    interests,
    saved: preferences.saved.filter(id => wordIds.has(id)),
    history: preferences.history.filter(item => wordIds.has(item.id)),
    hiddenWords: preferences.hiddenWords.filter(id => wordIds.has(id)),
    onboarded: preferences.onboarded && interests.length > 0,
  });
}

async function initialize() {
  try {
    const response = await fetch('/api/catalog');
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The vocabulary could not be loaded.');
    if (!Array.isArray(data.words) || !data.words.length || !data.collections?.length) throw new Error('The vocabulary database is empty.');
    catalog = data;
    sanitizePreferences();
    applyAppearance();
    calculateDaily();
    renderFooter();
    renderApp();
    if (!preferences.onboarded) showOnboarding();
    initialized = true;
    if (!storageAvailable) toast('Browser storage is unavailable. Changes will last for this visit only.');
    updateNetwork();
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => { /* Online learning remains available without offline caching. */ });
    }
  } catch (error) {
    main.innerHTML = `<section class="interior-page page-width empty-state"><span class="eyebrow">A SMALL PAUSE</span><h1 tabindex="-1">Your words need<br>a moment.</h1><p>${escape(error.message)}</p><p class="muted">If you’re offline, connect once to download the vocabulary. If you maintain this site, check data/words.json and the server log.</p><button class="button button-primary" data-action="retry">Try again ${icon('arrow')}</button></section>`;
    main.setAttribute('aria-busy', 'false');
  }
}

await initialize();
