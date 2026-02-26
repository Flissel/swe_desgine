// Minimal test
console.log("Starting...");
console.log("process.type:", process.type);
console.log("process.versions:", JSON.stringify(process.versions, null, 2));

// Try direct destructured import
try {
  const e = require('electron');
  console.log("require('electron') type:", typeof e);
  console.log("require('electron'):", e.toString().substring(0, 100));
} catch (err) {
  console.log("Error:", err.message);
}
