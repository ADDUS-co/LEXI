const paths = {
  asterisk: '<path d="M12 2v20M2 12h20M5 5l14 14M5 19 19 5"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  arrowUp: '<path d="M6 18 18 6M6 6h12v12"/>',
  down: '<path d="M12 4v16m-6-6 6 6 6-6"/>',
  bookmark: '<path d="M6 4h12v17l-6-4-6 4z"/>',
  settings: '<path d="m9 3-.7 2.4-2.1 1.2L3.8 6l-2 3.4L3.5 11v2L2 14.6 4 18l2.3-.6 2 1.2L9 21h4l.7-2.4 2-1.2 2.4.6 2-3.4-1.6-1.6v-2l1.6-1.6L18.2 6l-2.4.6-2.1-1.2L13 3z"/><circle cx="11" cy="12" r="3"/>',
  volume: '<path d="M11 4 6 8H3v8h3l5 4zM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  share: '<path d="M12 15V3m-4 4 4-4 4 4M5 12v8h14v-8"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  scales: '<path d="M12 3v18M5 21h14M4 6h16M5 6l-4 8h8zm14 0-4 8h8zM1 14a4 3 0 0 0 8 0m6 0a4 3 0 0 0 8 0"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="m16 8-2 6-6 2 2-6z"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="1"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4M10 10h4v4h-4z"/>',
  chart: '<path d="M3 3v18h18M7 14l5-5 4 3 5-7m-5 0h5v5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',
  search: '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
  history: '<path d="M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v6l4 2"/>',
  home: '<path d="m3 10 9-7 9 7v11h-7v-7h-4v7H3z"/>',
  grid: '<path d="M3 3h7v7H3zm11 0h7v7h-7zM3 14h7v7H3zm11 0h7v7h-7z"/>',
  instagram: '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17.5 6.5h.01"/>',
  send: '<path d="m3 10 18-7-7 18-3-8zm8 3L21 3"/>',
  phone: '<path d="m7 3 3 5-3 3a16 16 0 0 0 6 6l3-3 5 3-2 4C10 22 2 14 3 5z"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="1"/><path d="m2 5 10 8L22 5"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  spark: '<path d="M12 1 14.5 9.5 23 12l-8.5 2.5L12 23l-2.5-8.5L1 12l8.5-2.5z"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
};

export function icon(name, className = '') {
  return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.spark}</svg>`;
}
