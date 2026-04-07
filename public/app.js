/* ===== State ===== */
const state = {
  recipes: [],
  allCategories: [],
  allTags: [],
  filters: { search: '', category: '', tag: '' },
  editingId: null,
  formTags: [],
};

/* ===== API helpers ===== */
const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: 'DELETE' });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};

/* ===== DOM refs ===== */
const $ = id => document.getElementById(id);
const el = (tag, attrs = {}, ...children) => {
  const e = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k === 'text') e.textContent = v;
    else e.setAttribute(k, v);
  });
  children.forEach(c => c && e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c));
  return e;
};

/* ===== Date formatting ===== */
function fmtDate(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')}`;
}

/* ===== Render Recipes ===== */
function renderRecipes() {
  const grid = $('recipeGrid');
  const empty = $('emptyState');
  const count = $('recipeCount');
  const { search, category, tag } = state.filters;

  let list = state.recipes;
  if (search) {
    const q = search.toLowerCase();
    list = list.filter(r =>
      r.title.toLowerCase().includes(q) ||
      (r.description || '').toLowerCase().includes(q) ||
      (r.memo || '').toLowerCase().includes(q)
    );
  }
  if (category) list = list.filter(r => r.category === category);
  if (tag) list = list.filter(r => r.tags.includes(tag));

  grid.innerHTML = '';
  if (list.length === 0) {
    empty.style.display = '';
    count.textContent = '';
  } else {
    empty.style.display = 'none';
    count.textContent = `${list.length} 件`;
    list.forEach(r => grid.appendChild(createCard(r)));
  }
}

function createCard(r) {
  const card = el('div', { class: 'recipe-card' });

  // Thumbnail
  const thumb = el('div', { class: 'card-thumb' });
  if (r.image) {
    const img = el('img', { src: r.image, alt: r.title, loading: 'lazy' });
    img.onerror = () => { img.replaceWith(placeholder(r)); };
    thumb.appendChild(img);
  } else {
    thumb.appendChild(placeholder(r));
  }
  card.appendChild(thumb);

  // Body
  const body = el('div', { class: 'card-body' });

  // Meta: category + tags
  if (r.category || r.tags.length) {
    const meta = el('div', { class: 'card-meta' });
    if (r.category) meta.appendChild(el('span', { class: 'card-category', text: r.category }));
    r.tags.slice(0, 3).forEach(t => meta.appendChild(el('span', { class: 'card-tag', text: t })));
    body.appendChild(meta);
  }

  body.appendChild(el('div', { class: 'card-title', text: r.title }));
  if (r.description) body.appendChild(el('div', { class: 'card-desc', text: r.description }));

  const footer = el('div', { class: 'card-footer' });
  footer.appendChild(el('span', { class: 'card-date', text: fmtDate(r.created_at) }));
  if (r.memo) footer.appendChild(el('span', { class: 'card-memo-badge', html: '📝 メモあり' }));
  body.appendChild(footer);

  card.appendChild(body);
  card.addEventListener('click', () => openDetail(r.id));
  return card;
}

function placeholder(r) {
  const emojis = { '朝食':'🌅','昼食':'🍱','夕食':'🍽','デザート':'🍰','おやつ':'🍪','ドリンク':'☕','その他':'🍳' };
  return el('div', { class: 'card-thumb-placeholder', text: emojis[r.category] || '🍳' });
}

/* ===== Render Filters ===== */
async function loadMeta() {
  const meta = await api.get('/api/meta');
  state.allCategories = meta.categories;
  state.allTags = meta.tags;
  renderFilters();
}

function renderFilters() {
  const sel = $('categoryFilter');
  const currentCat = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  state.allCategories.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    if (c === currentCat) opt.selected = true;
    sel.appendChild(opt);
  });

  const row = $('tagFilterRow');
  const pills = $('tagFilterPills');
  pills.innerHTML = '';
  if (state.allTags.length) {
    row.style.display = '';
    state.allTags.forEach(t => {
      const pill = el('button', { class: 'tag-filter-pill' + (state.filters.tag === t ? ' active' : ''), text: t });
      pill.addEventListener('click', () => {
        state.filters.tag = state.filters.tag === t ? '' : t;
        renderFilters();
        renderRecipes();
      });
      pills.appendChild(pill);
    });
  } else {
    row.style.display = 'none';
  }
}

/* ===== Load all recipes ===== */
async function loadRecipes() {
  state.recipes = await api.get('/api/recipes');
  renderRecipes();
}

/* ===== Detail Modal ===== */
async function openDetail(id) {
  const r = await api.get(`/api/recipes?id=${id}`);
  const body = $('detailBody');
  body.innerHTML = '';

  if (r.image) {
    const img = el('img', { class: 'detail-hero', src: r.image, alt: r.title });
    img.onerror = () => img.remove();
    body.appendChild(img);
  }

  const content = el('div', { class: 'detail-content' });

  // Meta
  if (r.category || r.tags.length) {
    const meta = el('div', { class: 'detail-meta' });
    if (r.category) meta.appendChild(el('span', { class: 'detail-category', text: r.category }));
    r.tags.forEach(t => meta.appendChild(el('span', { class: 'detail-tag', text: t })));
    content.appendChild(meta);
  }

  content.appendChild(el('h2', { class: 'detail-title', text: r.title }));
  if (r.description) content.appendChild(el('p', { class: 'detail-desc', text: r.description }));

  // Ingredients
  if (r.ingredients && r.ingredients.length) {
    const sec = el('div', { class: 'detail-section' });
    sec.appendChild(el('div', { class: 'detail-section-title', text: '材料' }));
    const ul = el('ul', { class: 'detail-ingredients' });
    r.ingredients.forEach(i => ul.appendChild(el('li', { text: i })));
    sec.appendChild(ul);
    content.appendChild(sec);
  }

  // Instructions
  if (r.instructions) {
    const sec = el('div', { class: 'detail-section' });
    sec.appendChild(el('div', { class: 'detail-section-title', text: '作り方' }));
    sec.appendChild(el('div', { class: 'detail-instructions', text: r.instructions }));
    content.appendChild(sec);
  }

  // Memo
  if (r.memo) {
    const sec = el('div', { class: 'detail-section' });
    sec.appendChild(el('div', { class: 'detail-section-title', text: '📝 メモ' }));
    sec.appendChild(el('div', { class: 'detail-memo', text: r.memo }));
    content.appendChild(sec);
  }

  // Source URL
  if (r.url) {
    const src = el('div', { class: 'detail-source' });
    src.appendChild(document.createTextNode('出典: '));
    const a = el('a', { href: r.url, target: '_blank', rel: 'noopener', text: r.url });
    src.appendChild(a);
    content.appendChild(src);
  }

  content.appendChild(el('div', { class: 'detail-date', text: `保存日: ${fmtDate(r.created_at)}` }));
  body.appendChild(content);

  $('editFromDetailBtn').dataset.id = id;
  openOverlay('detailOverlay');
}

/* ===== Form Modal ===== */
function openAddModal() {
  state.editingId = null;
  state.formTags = [];
  $('modalTitle').textContent = 'レシピを追加';
  $('deleteBtn').style.display = 'none';
  $('formId').value = '';
  $('formUrl').value = '';
  $('urlInput').value = '';
  resetFetchStatus();
  showStep('stepUrl');
  openOverlay('formOverlay');
}

async function openEditModal(id) {
  const r = await api.get(`/api/recipes?id=${id}`);
  state.editingId = id;
  state.formTags = [...r.tags];

  $('modalTitle').textContent = 'レシピを編集';
  $('deleteBtn').style.display = '';
  $('formId').value = id;
  $('formUrl').value = r.url || '';
  $('formTitle').value = r.title;
  $('formCategory').value = r.category || '';
  $('formDescription').value = r.description || '';
  $('formInstructions').value = r.instructions || '';
  $('formMemo').value = r.memo || '';
  $('formImage').value = r.image || '';

  updateImagePreview(r.image);
  renderFormTags();
  renderIngredients(r.ingredients || []);

  showStep('stepForm');
  openOverlay('formOverlay');
}

function updateImagePreview(src) {
  const header = $('imageHeader');
  const img = $('previewImg');
  if (src) {
    img.src = src;
    img.onerror = () => { header.style.display = 'none'; };
    img.onload = () => { header.style.display = ''; };
  } else {
    header.style.display = 'none';
  }
}

function showStep(stepId) {
  $('stepUrl').style.display = stepId === 'stepUrl' ? '' : 'none';
  $('stepForm').style.display = stepId === 'stepForm' ? '' : 'none';
}

function resetFetchStatus() {
  const s = $('fetchStatus');
  s.style.display = 'none';
  s.className = 'fetch-status';
  s.innerHTML = '';
}

function setFetchStatus(type, msg) {
  const s = $('fetchStatus');
  s.style.display = '';
  s.className = `fetch-status ${type}`;
  s.innerHTML = type === 'loading'
    ? `<div class="spinner"></div><span>${msg}</span>`
    : `<span>${msg}</span>`;
}

/* ===== Tag input ===== */
function renderFormTags() {
  const chips = $('formTagChips');
  chips.innerHTML = '';
  state.formTags.forEach((t, i) => {
    const chip = el('span', { class: 'tag-chip', text: t });
    const rm = el('button', { class: 'tag-chip-remove', type: 'button', html: '&times;' });
    rm.addEventListener('click', () => { state.formTags.splice(i, 1); renderFormTags(); });
    chip.appendChild(rm);
    chips.appendChild(chip);
  });
}

$('formTagInput').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    const val = e.target.value.trim().replace(/,$/, '');
    if (val && !state.formTags.includes(val)) {
      state.formTags.push(val);
      renderFormTags();
    }
    e.target.value = '';
  }
});
$('formTagWrap').addEventListener('click', () => $('formTagInput').focus());

/* ===== Ingredients ===== */
function renderIngredients(items) {
  const list = $('ingredientsList');
  list.innerHTML = '';
  (items.length ? items : ['']).forEach(val => addIngredientRow(val));
}

function addIngredientRow(val = '') {
  const list = $('ingredientsList');
  const row = el('div', { class: 'ingredient-item' });
  const input = el('input', { type: 'text', class: 'ingredient-input', placeholder: '例: 鶏もも肉 200g' });
  input.value = val;
  const rm = el('button', { type: 'button', class: 'ingredient-remove', html: '&times;' });
  rm.addEventListener('click', () => row.remove());
  row.appendChild(input);
  row.appendChild(rm);
  list.appendChild(row);
  return input;
}

function getIngredients() {
  return [...$('ingredientsList').querySelectorAll('.ingredient-input')]
    .map(i => i.value.trim())
    .filter(Boolean);
}

$('addIngredientBtn').addEventListener('click', () => {
  const input = addIngredientRow();
  input.focus();
});

/* ===== Image URL preview update ===== */
$('formImage').addEventListener('change', e => updateImagePreview(e.target.value));
$('formImage').addEventListener('input', e => {
  clearTimeout($('formImage')._timer);
  $('formImage')._timer = setTimeout(() => updateImagePreview(e.target.value), 500);
});

/* ===== Fetch from URL ===== */
$('fetchBtn').addEventListener('click', async () => {
  const url = $('urlInput').value.trim();
  if (!url) return;
  setFetchStatus('loading', 'レシピを取得中...');
  $('fetchBtn').disabled = true;
  try {
    const data = await api.post('/api/fetch', { url });
    state.formTags = [];
    $('formTitle').value = data.title || '';
    $('formDescription').value = data.description || '';
    $('formInstructions').value = data.instructions || '';
    $('formImage').value = data.image || '';
    $('formUrl').value = url;
    renderIngredients(data.ingredients || []);
    renderFormTags();
    updateImagePreview(data.image);
    setFetchStatus('success', '✓ 取得しました！内容を確認して保存してください');
    setTimeout(() => {
      showStep('stepForm');
      resetFetchStatus();
    }, 800);
  } catch (err) {
    setFetchStatus('error', '⚠ 取得に失敗しました。手動で入力してください。');
    console.error(err);
  } finally {
    $('fetchBtn').disabled = false;
  }
});

$('urlInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') $('fetchBtn').click();
});

$('skipFetchBtn').addEventListener('click', () => {
  $('formUrl').value = $('urlInput').value.trim();
  $('formTitle').value = '';
  $('formDescription').value = '';
  $('formInstructions').value = '';
  $('formImage').value = '';
  state.formTags = [];
  renderIngredients([]);
  renderFormTags();
  updateImagePreview('');
  showStep('stepForm');
});

$('backToUrlBtn').addEventListener('click', () => showStep('stepUrl'));

/* ===== Save ===== */
$('saveBtn').addEventListener('click', async () => {
  const title = $('formTitle').value.trim();
  if (!title) { $('formTitle').focus(); return; }

  const payload = {
    url: $('formUrl').value.trim(),
    title,
    description: $('formDescription').value.trim(),
    image: $('formImage').value.trim(),
    ingredients: getIngredients(),
    instructions: $('formInstructions').value.trim(),
    category: $('formCategory').value,
    tags: state.formTags,
    memo: $('formMemo').value.trim(),
  };

  $('saveBtn').disabled = true;
  $('saveBtn').textContent = '保存中...';
  try {
    if (state.editingId) {
      await api.put(`/api/recipes?id=${state.editingId}`, payload);
    } else {
      await api.post('/api/recipes', payload);
    }
    closeOverlay('formOverlay');
    closeOverlay('detailOverlay');
    await loadRecipes();
    await loadMeta();
  } catch (err) {
    alert('保存に失敗しました: ' + err.message);
  } finally {
    $('saveBtn').disabled = false;
    $('saveBtn').textContent = '保存する';
  }
});

/* ===== Delete ===== */
$('deleteBtn').addEventListener('click', async () => {
  if (!state.editingId) return;
  if (!confirm('このレシピを削除しますか？')) return;
  try {
    await api.del(`/api/recipes?id=${state.editingId}`);
    closeOverlay('formOverlay');
    closeOverlay('detailOverlay');
    await loadRecipes();
    await loadMeta();
  } catch (err) {
    alert('削除に失敗しました: ' + err.message);
  }
});

/* ===== Edit from detail ===== */
$('editFromDetailBtn').addEventListener('click', () => {
  const id = $('editFromDetailBtn').dataset.id;
  closeOverlay('detailOverlay');
  if (id) openEditModal(parseInt(id));
});

/* ===== Overlay open/close ===== */
function openOverlay(id) {
  const o = $(id);
  o.setAttribute('aria-hidden', 'false');
  o.classList.add('open');
  document.body.style.overflow = 'hidden';
}
function closeOverlay(id) {
  const o = $(id);
  o.setAttribute('aria-hidden', 'true');
  o.classList.remove('open');
  if (!$('formOverlay').classList.contains('open') && !$('detailOverlay').classList.contains('open')) {
    document.body.style.overflow = '';
  }
}

$('formClose').addEventListener('click', () => closeOverlay('formOverlay'));
$('detailClose').addEventListener('click', () => closeOverlay('detailOverlay'));

// Close on backdrop click
['formOverlay', 'detailOverlay'].forEach(id => {
  $(id).addEventListener('click', e => { if (e.target === $(id)) closeOverlay(id); });
});

// Close on Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if ($('detailOverlay').classList.contains('open')) closeOverlay('detailOverlay');
    else if ($('formOverlay').classList.contains('open')) closeOverlay('formOverlay');
  }
});

/* ===== Add button ===== */
$('addBtn').addEventListener('click', openAddModal);
$('emptyAddBtn').addEventListener('click', openAddModal);

/* ===== Filters ===== */
let searchTimer;
$('searchInput').addEventListener('input', e => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    state.filters.search = e.target.value.trim();
    renderRecipes();
  }, 250);
});

$('categoryFilter').addEventListener('change', e => {
  state.filters.category = e.target.value;
  renderRecipes();
});

/* ===== Init ===== */
(async () => {
  await loadRecipes();
  await loadMeta();
})();
