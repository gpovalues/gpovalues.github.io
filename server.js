/**
 * GPO Values & Trade Calculator - Local HTTP Server
 * Zero-dependency native Node.js static server
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = process.env.HOST || '0.0.0.0';

const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg',
  '.txt': 'text/plain; charset=utf-8',
  '.xml': 'application/xml; charset=utf-8'
};

const server = http.createServer((req, res) => {
  // Normalize request URL and remove query params / hash
  let cleanPath = req.url.split('?')[0].split('#')[0];
  if (cleanPath === '/' || cleanPath === '') {
    cleanPath = '/index.html';
  }

  // Prevent directory traversal attacks
  const safePath = path.normalize(cleanPath).replace(/^(\.\.[\/\\])+/, '');
  const filePath = path.join(__dirname, safePath);

  fs.stat(filePath, (err, stats) => {
    if (err || !stats.isFile()) {
      res.writeHead(404, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(`<!DOCTYPE html><html><head><title>404 Not Found</title></head><body style="background:#090d16;color:#fff;font-family:sans-serif;text-align:center;padding:50px;"><h1>404 - File Not Found</h1><p><a href="/" style="color:#f59e0b;">Return to GPO Values Home</a></p></body></html>`);
      return;
    }

    const ext = path.extname(filePath).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';

    // Cache control
    const headers = {
      'Content-Type': contentType,
      'Content-Length': stats.size,
      'Access-Control-Allow-Origin': '*'
    };

    if (ext === '.png' || ext === '.wav' || ext === '.svg' || ext === '.ico') {
      headers['Cache-Control'] = 'public, max-age=86400';
    } else {
      headers['Cache-Control'] = 'no-cache, must-revalidate';
    }

    res.writeHead(200, headers);
    const stream = fs.createReadStream(filePath);
    stream.pipe(res);
  });
});

server.listen(PORT, HOST, () => {
  console.log('====================================================');
  console.log(`🏴‍☠️ GPO Values & Trade Calculator Server Started!`);
  console.log(`🌐 Local:   http://localhost:${PORT}`);
  console.log(`🌐 Network: http://${HOST}:${PORT}`);
  console.log('====================================================');
});
