console.log("process.versions.electron:", process.versions.electron);
console.log("typeof global.electron:", typeof global.electron);
console.log("global keys:", Object.keys(global).filter(k => k.includes('electron') || k.includes('Electron')));
console.log("process keys:", Object.keys(process).filter(k => k.includes('electron') || k.includes('Electron') || k.includes('binding')));

// Try process._linkedBinding
if (process._linkedBinding) {
  console.log("Has _linkedBinding");
  try {
    const app = process._linkedBinding('electron_browser_app');
    console.log("app from binding:", app);
  } catch(e) {
    console.log("binding error:", e.message);
  }
}

// Check module paths
console.log("Module paths:", module.paths.slice(0, 3));

// Try requiring with absolute path to electron built-in
try {
  const e = require('electron');
  console.log("require('electron'):", typeof e, e.toString().substring(0,50));
} catch(err) {
  console.log("require error:", err.message);
}

setTimeout(() => process.exit(0), 1000);
