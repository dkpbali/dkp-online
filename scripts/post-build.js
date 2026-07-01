import fs from 'fs';
import path from 'path';

const distDir = path.resolve('dist');

// Recursive function to scan all files in dist/
function getFiles(dir, files = []) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const res = path.resolve(dir, entry.name);
    if (entry.isDirectory()) {
      getFiles(res, files);
    } else {
      let relPath = path.relative(distDir, res).replace(/\\/g, '/');
      // sw.js should not precache itself
      if (relPath !== 'sw.js' && !relPath.startsWith('.git')) {
        files.push(relPath);
      }
    }
  }
  return files;
}

const buildFiles = getFiles(distDir);
buildFiles.unshift('./');

const swPath = path.join(distDir, 'sw.js');
if (fs.existsSync(swPath)) {
  let swContent = fs.readFileSync(swPath, 'utf8');
  
  // Inject PRECACHE_URLS array
  const filesJson = JSON.stringify(buildFiles, null, 2);
  swContent = swContent.replace(
    /const PRECACHE_URLS = \[[\s\S]*?\];/,
    `const PRECACHE_URLS = ${filesJson};`
  );
  
  // Update Cache Version with unique Build Timestamp
  const buildId = new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14);
  swContent = swContent.replace(
    /const CACHE_NAME = "aruniwaves-v\d+";/,
    `const CACHE_NAME = "aruniwaves-v${buildId}";`
  );
  
  fs.writeFileSync(swPath, swContent, 'utf8');
  console.log(`\x1b[32m[Post-Build] Berhasil menyuntikkan ${buildFiles.length} aset ke sw.js (Versi: v${buildId})\x1b[0m`);
} else {
  console.warn('[Post-Build] Peringatan: sw.js tidak ditemukan di dist/');
}
