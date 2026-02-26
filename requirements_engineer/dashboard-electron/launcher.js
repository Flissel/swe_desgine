/**
 * Electron Launcher
 *
 * This script launches Electron with the bundled main process file.
 * It temporarily renames node_modules/electron to avoid shadowing
 * Electron's built-in module.
 */

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const electronDir = path.join(__dirname, 'node_modules/electron');
const electronDirBackup = path.join(__dirname, 'node_modules/_electron_bak');
const electronExe = path.join(electronDir, 'dist/electron.exe');

// Check if electron exists
if (!fs.existsSync(electronExe)) {
  console.error('Electron not found at:', electronExe);
  process.exit(1);
}

// Rename node_modules/electron
console.log('[Launcher] Temporarily renaming node_modules/electron...');
try {
  if (fs.existsSync(electronDirBackup)) {
    fs.rmSync(electronDirBackup, { recursive: true, force: true });
  }
  fs.renameSync(electronDir, electronDirBackup);
} catch (err) {
  console.error('[Launcher] Failed to rename:', err.message);
  process.exit(1);
}

// Spawn Electron with the current directory (reads package.json)
console.log('[Launcher] Starting Electron...');
const electronExeNew = path.join(electronDirBackup, 'dist/electron.exe');

const child = spawn(electronExeNew, ['.'], {
  cwd: __dirname,
  stdio: 'inherit',
  env: {
    ...process.env,
    NODE_ENV: process.env.NODE_ENV || 'production'
  }
});

child.on('close', (code) => {
  console.log('[Launcher] Electron exited with code:', code);
  // Restore
  try {
    if (fs.existsSync(electronDirBackup)) {
      fs.renameSync(electronDirBackup, electronDir);
      console.log('[Launcher] Restored node_modules/electron');
    }
  } catch (err) {
    console.error('[Launcher] Failed to restore:', err.message);
  }
  process.exit(code || 0);
});

child.on('error', (err) => {
  console.error('[Launcher] Error:', err);
  try {
    if (fs.existsSync(electronDirBackup)) {
      fs.renameSync(electronDirBackup, electronDir);
    }
  } catch (e) {
    console.error('[Launcher] Failed to restore:', e.message);
  }
  process.exit(1);
});
