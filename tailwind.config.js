/** tailwind.config.js (Tailwind v3) — na raiz do projeto Django */
module.exports = {
  darkMode: 'class',
  content: [
    './templates/**/*.html',
    './*/templates/**/*.html',
    './apps/*/templates/**/*.html',
    './static/js/**/*.js',
  ],
  // Classes montadas dinamicamente em JS/Python que o scanner não vê
  safelist: [
    'animate-pulse',
    { pattern: /^(bg|text)-(red|yellow|green|blue)-(50|200|400|500|800|900)$/ },
  ],
  theme: { extend: {} },
};