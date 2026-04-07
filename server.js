const express = require('express');
const Database = require('better-sqlite3');
const fetch = require('node-fetch');
const cheerio = require('cheerio');
const path = require('path');

const app = express();
const db = new Database(path.join(__dirname, 'db', 'recipes.db'));

db.exec(`
  CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    image TEXT DEFAULT '',
    ingredients TEXT DEFAULT '[]',
    instructions TEXT DEFAULT '',
    category TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    memo TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Scrape recipe data from URL
app.post('/api/fetch', async (req, res) => {
  const { url } = req.body;
  if (!url) return res.status(400).json({ error: 'URLが必要です' });

  try {
    const response = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja,en;q=0.5',
      },
      timeout: 15000,
      redirect: 'follow',
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const html = await response.text();
    const $ = cheerio.load(html);

    const recipe = { url, title: '', description: '', image: '', ingredients: [], instructions: '' };

    // Try JSON-LD schema.org/Recipe
    $('script[type="application/ld+json"]').each((_, el) => {
      try {
        const raw = $(el).html();
        const data = JSON.parse(raw);
        const items = Array.isArray(data) ? data : (data['@graph'] || [data]);
        const r = items.find(d => d && (d['@type'] === 'Recipe' || (Array.isArray(d['@type']) && d['@type'].includes('Recipe'))));
        if (!r) return;

        if (r.name) recipe.title = r.name;
        if (r.description) recipe.description = r.description;

        const img = Array.isArray(r.image) ? r.image[0] : r.image;
        if (img) recipe.image = typeof img === 'object' ? (img.url || '') : img;

        if (Array.isArray(r.recipeIngredient)) recipe.ingredients = r.recipeIngredient;

        if (r.recipeInstructions) {
          if (Array.isArray(r.recipeInstructions)) {
            recipe.instructions = r.recipeInstructions
              .map((s, i) => `${i + 1}. ${typeof s === 'string' ? s : (s.text || '')}`)
              .join('\n');
          } else if (typeof r.recipeInstructions === 'string') {
            recipe.instructions = r.recipeInstructions;
          }
        }
      } catch (_) {}
    });

    // Fallback: OGP / meta tags
    if (!recipe.title) {
      recipe.title =
        $('meta[property="og:title"]').attr('content') ||
        $('meta[name="twitter:title"]').attr('content') ||
        $('title').text().trim() ||
        '無題のレシピ';
    }
    if (!recipe.description) {
      recipe.description =
        $('meta[property="og:description"]').attr('content') ||
        $('meta[name="description"]').attr('content') ||
        '';
    }
    if (!recipe.image) {
      recipe.image =
        $('meta[property="og:image"]').attr('content') ||
        $('meta[name="twitter:image"]').attr('content') ||
        '';
    }

    // Clean up
    recipe.title = recipe.title.replace(/\s+/g, ' ').trim();
    recipe.description = recipe.description.replace(/\s+/g, ' ').trim();

    res.json(recipe);
  } catch (err) {
    res.status(500).json({ error: '取得に失敗しました: ' + err.message });
  }
});

// List recipes
app.get('/api/recipes', (req, res) => {
  const { category, tag, search } = req.query;
  let query = 'SELECT * FROM recipes WHERE 1=1';
  const params = [];

  if (category) {
    query += ' AND category = ?';
    params.push(category);
  }
  if (search) {
    query += ' AND (title LIKE ? OR description LIKE ? OR memo LIKE ?)';
    params.push(`%${search}%`, `%${search}%`, `%${search}%`);
  }
  query += ' ORDER BY created_at DESC';

  let rows = db.prepare(query).all(...params);
  rows = rows.map(r => ({
    ...r,
    ingredients: JSON.parse(r.ingredients || '[]'),
    tags: JSON.parse(r.tags || '[]'),
  }));

  if (tag) rows = rows.filter(r => r.tags.includes(tag));

  res.json(rows);
});

// Get single recipe
app.get('/api/recipes/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM recipes WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'Not found' });
  res.json({ ...row, ingredients: JSON.parse(row.ingredients || '[]'), tags: JSON.parse(row.tags || '[]') });
});

// Create recipe
app.post('/api/recipes', (req, res) => {
  const { url, title, description, image, ingredients, instructions, category, tags, memo } = req.body;
  const result = db.prepare(`
    INSERT INTO recipes (url, title, description, image, ingredients, instructions, category, tags, memo)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    url || '', title, description || '', image || '',
    JSON.stringify(ingredients || []), instructions || '',
    category || '', JSON.stringify(tags || []), memo || ''
  );
  const row = db.prepare('SELECT * FROM recipes WHERE id = ?').get(result.lastInsertRowid);
  res.json({ ...row, ingredients: JSON.parse(row.ingredients), tags: JSON.parse(row.tags) });
});

// Update recipe
app.put('/api/recipes/:id', (req, res) => {
  const { title, description, image, ingredients, instructions, category, tags, memo } = req.body;
  db.prepare(`
    UPDATE recipes
    SET title=?, description=?, image=?, ingredients=?, instructions=?, category=?, tags=?, memo=?,
        updated_at=CURRENT_TIMESTAMP
    WHERE id=?
  `).run(
    title, description || '', image || '',
    JSON.stringify(ingredients || []), instructions || '',
    category || '', JSON.stringify(tags || []), memo || '',
    req.params.id
  );
  const row = db.prepare('SELECT * FROM recipes WHERE id = ?').get(req.params.id);
  res.json({ ...row, ingredients: JSON.parse(row.ingredients), tags: JSON.parse(row.tags) });
});

// Delete recipe
app.delete('/api/recipes/:id', (req, res) => {
  db.prepare('DELETE FROM recipes WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

// All categories and tags (for filter UI)
app.get('/api/meta', (req, res) => {
  const rows = db.prepare('SELECT category, tags FROM recipes').all();
  const categories = [...new Set(rows.map(r => r.category).filter(Boolean))].sort();
  const tags = [...new Set(rows.flatMap(r => JSON.parse(r.tags || '[]')))].sort();
  res.json({ categories, tags });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n🍳 レシピアプリ起動中 → http://localhost:${PORT}\n`);
});
