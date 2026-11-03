/** Local preview of public site files only. Collector state never becomes a route. */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const files = new Set(['index.html', 'style.css', 'app.js', 'icons.js', 'translations.js',
  'site_config.js', 'ads.js', 'ads.txt', 'robots.txt', 'sitemap.xml', 'data/values.json', 'data/history.json']);
const mime = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.webp': 'image/webp', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.wav': 'audio/wav',
  '.txt': 'text/plain; charset=utf-8', '.xml': 'application/xml; charset=utf-8' };

function createServer(root = __dirname) {
  return http.createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, { Allow: 'GET, HEAD' }); response.end(); return;
    }
    let relative;
    try {
      const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
      relative = path.posix.normalize(pathname).replace(/^\/+/, '') || 'index.html';
    } catch { response.writeHead(400); response.end('Invalid URL'); return; }
    const asset = /^(images|audio|fonts)\/[a-zA-Z0-9_./-]+\.(webp|png|jpe?g|svg|woff2|wav)$/.test(relative);
    const license = /^fonts\/(Finger-Paint|PT-Sans|Neucha)-OFL\.txt$/.test(relative);
    if (/(^|\/)\./.test(relative) || (!files.has(relative) && !asset && !license)) {
      response.writeHead(404); response.end('Not found'); return;
    }
    const filename = path.join(root, relative);
    let stat;
    try { stat = await fs.promises.stat(filename); if (!stat.isFile()) throw new Error(); }
    catch { response.writeHead(404); response.end('Not found'); return; }
    const ext = path.extname(relative);
    const etag = `W/"${stat.size.toString(16)}-${Math.floor(stat.mtimeMs).toString(16)}"`;
    response.setHeader('ETag', etag);
    response.setHeader('Cache-Control', ['.html', '.json', '.js', '.css'].includes(ext) ? 'no-cache' : 'public, max-age=86400');
    if (request.headers['if-none-match'] === etag) { response.writeHead(304); response.end(); return; }
    response.writeHead(200, { 'Content-Type': mime[ext] || 'application/octet-stream', 'Content-Length': stat.size });
    if (request.method === 'HEAD') { response.end(); return; }
    const stream = fs.createReadStream(filename);
    stream.on('error', () => response.destroy());
    stream.pipe(response);
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  const host = process.env.HOST || '127.0.0.1';
  const server = createServer();
  server.listen(port, host, () => console.log(`GPO Values: http://${host}:${server.address().port}`));
}

module.exports = { createServer };
