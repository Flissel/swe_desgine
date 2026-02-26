/**
 * Electron Runner
 *
 * This script moves node_modules/electron out of the way before running,
 * so that require('electron') properly resolves to Electron's built-in module.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const electronDir = path.join(__dirname, 'node_modules', 'electron');
const electronBackup = path.join(__dirname, '.electron-npm');
const electronExe = path.join(electronDir, 'dist', 'electron.exe');

// Check if electron exists
if (!fs.existsSync(electronExe)) {
  console.error('Electron not found. Run: npm install');
  process.exit(1);
}

// Move node_modules/electron to .electron-npm
console.log('[Runner] Moving node_modules/electron...');
try {
  if (fs.existsSync(electronBackup)) {
    fs.rmSync(electronBackup, { recursive: true, force: true });
  }
  fs.renameSync(electronDir, electronBackup);
} catch (err) {
  console.error('[Runner] Failed to move:', err.message);
  process.exit(1);
}

// Start Electron from the backup location
const electronExeNew = path.join(electronBackup, 'dist', 'electron.exe');
console.log('[Runner] Starting Electron from:', electronExeNew);

const args = process.argv.slice(2);
if (args.length === 0) {
  args.push('.');
}

const child = spawn(electronExeNew, args, {
  cwd: __dirname,
  stdio: 'inherit',
  env: {
    ...process.env,
    NODE_ENV: process.env.NODE_ENV || 'development'
  }
});

function restore() {
  console.log('[Runner] Restoring node_modules/electron...');
  try {
    if (fs.existsSync(electronBackup)) {
      if (fs.existsSync(electronDir)) {
        fs.rmSync(electronDir, { recursive: true, force: true });
      }
      fs.renameSync(electronBackup, electronDir);
    }
  } catch (err) {
    console.error('[Runner] Restore failed:', err.message);
  }
}

child.on('close', (code) => {
  restore();
  process.exit(code || 0);
});

child.on('error', (err) => {
  console.error('[Runner] Error:', err);
  restore();
  process.exit(1);
});

process.on('SIGINT', () => {
  child.kill('SIGINT');
});

process.on('SIGTERM', () => {
  child.kill('SIGTERM');
});
