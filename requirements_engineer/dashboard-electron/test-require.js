console.log("Testing module resolution...");

// Check what modules are in cache
const cacheKeys = Object.keys(require.cache);
console.log("Cache has", cacheKeys.length, "entries");
const electronKeys = cacheKeys.filter(k => k.includes('electron'));
console.log("Electron-related:", electronKeys);

// Try to find internal electron
try {
  // Maybe electron exposes itself differently
  const Module = require('module');
  console.log("Module._cache keys:", Object.keys(Module._cache).filter(k => k.includes('electron')));
} catch(e) {}

// Try different require paths
const paths = [
  'electron/main',
  'electron/common',
  '@electron/app',
  'electron:app'
];

for (const p of paths) {
  try {
    const m = require(p);
    console.log(`require('${p}'):`, m);
  } catch(e) {
    console.log(`require('${p}'): ERROR -`, e.code || e.message);
  }
}

process.exit(0);
