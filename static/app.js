'use strict';
const form = document.getElementById('analyze-form');
if (form) form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = form.querySelector('button');
  const output = document.getElementById('analysis-result');
  button.disabled = true;
  output.replaceChildren();
  output.textContent = 'Reading your review…';
  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: {'Content-Type':'application/json', 'X-CSRFToken':document.querySelector('meta[name="csrf-token"]').content},
      body: JSON.stringify({text:document.getElementById('review-input').value, save:document.getElementById('save-analysis')?.checked || false})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Analysis could not be completed.');
    output.replaceChildren();
    const label = document.createElement('strong');
    label.className = `result-label ${data.label.toLowerCase()}`;
    label.textContent = data.label;
    const description = document.createElement('p');
    description.textContent = `Positive estimate: ${(data.positive_probability*100).toFixed(1)}% · Negative: ${(data.negative_probability*100).toFixed(1)}%`;
    const note = document.createElement('p');
    note.className = 'fineprint';
    note.textContent = `Uncalibrated binary model estimates.${data.saved ? ' Saved to your private history.' : ' This analysis was not saved.'}`;
    output.append(label, description, note);
  } catch (error) {
    output.textContent = error.message || 'Connection failed. Please try again.';
  } finally {
    button.disabled = false;
  }
});

// Live movie search. Results are created with DOM text nodes, never HTML from the API.
for (const shell of document.querySelectorAll('[data-movie-search]')) {
  const input = shell.querySelector('input[name="q"]');
  const panel = shell.querySelector('.suggestions-panel');
  const list = shell.querySelector('[role="listbox"]');
  const status = shell.querySelector('.suggestion-status');
  const all = shell.querySelector('.all-results');
  const clear = shell.querySelector('.clear-search');
  const searchForm = shell.querySelector('form');
  let timer, controller, serial = 0, active = -1, links = [], lastQuery = '';
  function hide() {
    panel.hidden = true; input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant'); active = -1;
    for (const link of links) link.setAttribute('aria-selected', 'false');
  }
  function open() { panel.hidden = false; input.setAttribute('aria-expanded', 'true'); }
  function activate(index) {
    if (!links.length) return;
    active = (index + links.length) % links.length;
    links.forEach((link, i) => link.setAttribute('aria-selected', String(i === active)));
    input.setAttribute('aria-activedescendant', links[active].id);
    links[active].scrollIntoView({block:'nearest'});
  }
  function message(text) { list.replaceChildren(); links = []; active = -1; status.textContent = text; all.hidden = true; }
  async function lookup(query, id) {
    controller = new AbortController();
    try {
      const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {signal:controller.signal});
      const data = await response.json();
      if (id !== serial || input.value.trim() !== query) return;
      if (!response.ok) throw new Error(data.error || 'Search is unavailable. Please try again.');
      list.replaceChildren(); links = []; active = -1; input.removeAttribute('aria-activedescendant');
      status.textContent = data.results.length ? `${data.results.length} movie match${data.results.length === 1 ? '' : 'es'}` : 'No movies found. Try a different spelling.';
      data.results.forEach((movie, index) => {
        const link = document.createElement('a'); link.href = movie.url;
        link.className = 'suggestion-option'; link.id = `movie-option-${index}`;
        link.setAttribute('role','option'); link.setAttribute('aria-selected','false'); link.tabIndex = -1;
        if (movie.poster_path && /^\/[A-Za-z0-9._-]+$/.test(movie.poster_path)) {
          const poster = document.createElement('img'); poster.className = 'suggestion-poster';
          poster.src = `https://image.tmdb.org/t/p/w92${movie.poster_path}`; poster.alt = ''; link.append(poster);
        } else {
          const poster = document.createElement('span'); poster.className = 'suggestion-poster suggestion-placeholder';
          poster.textContent = '◈'; poster.setAttribute('aria-hidden','true'); link.append(poster);
        }
        const text = document.createElement('span'); text.className = 'suggestion-text';
        const title = document.createElement('span'); title.className = 'suggestion-title'; title.textContent = movie.title;
        const meta = document.createElement('span'); meta.className = 'suggestion-meta';
        meta.textContent = [movie.year || 'Year unavailable', ...(movie.genres || [])].join(' · ');
        text.append(title, meta); link.append(text);
        if (movie.rating > 0) { const rating=document.createElement('span'); rating.className='suggestion-rating'; rating.textContent=`★ ${Number(movie.rating).toFixed(1)}`; link.append(rating); }
        const arrow = document.createElement('span'); arrow.className='suggestion-arrow'; arrow.textContent='↗'; arrow.setAttribute('aria-hidden','true'); link.append(arrow);
        link.addEventListener('mousemove', () => { active=index; links.forEach((x,i)=>x.setAttribute('aria-selected',String(i===index))); input.setAttribute('aria-activedescendant',link.id); });
        list.append(link); links.push(link);
      });
      all.href = `/?q=${encodeURIComponent(query)}`; all.hidden = !data.results.length;
      lastQuery = query;
      // Do not reopen if the user moved focus outside while the request was pending.
      if (shell.contains(document.activeElement)) open();
    } catch (error) {
      if (error.name === 'AbortError' || id !== serial) return;
      message(error.message || 'Could not load movies. Please try again.');
    }
  }
  input.addEventListener('input', () => {
    clearTimeout(timer); controller?.abort(); serial++; lastQuery = '';
    clear.hidden = !input.value;
    input.removeAttribute('aria-activedescendant');
    const query = input.value.trim();
    if (query.length < 2) { hide(); list.replaceChildren(); links = []; return; }
    open(); message('Finding movies…');
    const id = serial; timer = setTimeout(() => lookup(query, id), 300);
  });
  input.addEventListener('focus', () => {
    if (input.value.trim().length >= 2) {
      if (lastQuery === input.value.trim()) open();
      else input.dispatchEvent(new Event('input'));
    }
  });
  input.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      clearTimeout(timer); controller?.abort(); serial++; hide();
    } else if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && links.length) {
      event.preventDefault(); open(); activate(active < 0 ? (event.key === 'ArrowDown' ? 0 : links.length - 1) : active + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Enter' && !panel.hidden && active >= 0) {
      event.preventDefault(); window.location.assign(links[active].href);
    }
  });
  searchForm.addEventListener('submit', () => { clearTimeout(timer); controller?.abort(); hide(); });
  clear.addEventListener('click', () => { input.value=''; input.dispatchEvent(new Event('input')); input.focus(); });
  document.addEventListener('pointerdown', event => { if (!shell.contains(event.target)) hide(); });
  shell.addEventListener('focusout', () => { setTimeout(() => { if (!shell.contains(document.activeElement)) hide(); }, 0); });
  clear.hidden = !input.value;
}

// Keep the layout useful when the movie image CDN is unreachable.
function replaceUnavailableImage(image) {
  if (!(image instanceof HTMLImageElement)) return;
  if (image.classList.contains('stage-backdrop')) { image.hidden = true; return; }
  const suggestion = image.classList.contains('suggestion-poster');
  const mainPoster = image.classList.contains('mainposter');
  if (!suggestion && !mainPoster && !image.closest('.posterwrap')) return;
  const fallback = document.createElement('div');
  fallback.className = suggestion ? 'suggestion-poster suggestion-placeholder' : mainPoster ? 'mainposter noposter' : 'noposter';
  const icon = document.createElement('span'); icon.textContent = '◈'; fallback.append(icon);
  if (!suggestion) {
    const title = document.createElement('b'); title.textContent = image.alt.replace(/ poster$/, '') || 'Poster unavailable';
    fallback.append(title);
  }
  fallback.setAttribute('role','img'); fallback.setAttribute('aria-label', image.alt || 'Movie poster unavailable');
  image.replaceWith(fallback);
}
document.addEventListener('error', event => replaceUnavailableImage(event.target), true);
for (const image of document.images) {
  if (image.complete && image.naturalWidth === 0) replaceUnavailableImage(image);
}
