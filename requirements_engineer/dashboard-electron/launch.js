/**
 * Electron Launch Script
 *
 * This script removes the problematic node_modules/electron package
 * (keeping only the electron.exe binary) so that require('electron')
 * properly resolves to Electron's built-in module.
 */

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

const electronDir = path.join(__dirname, 'node_modules', 'electron');
const electronDist = path.join(electronDir, 'dist');
const electronExe = path.join(electronDist, 'electron.exe');

// Backup location (outside node_modules/electron)
const backupDir = path.join(__dirname, '.electron-backup');

// Files to preserve/backup
const filesToBackup = ['package.json', 'index.js', 'cli.js', 'install.js', 'electron.d.ts'];

if (!fs.existsSync(electronExe)) {
  console.error('[Launch] Electron binary not found at:', electronExe);
  process.exit(1);
}

// Backup critical files
console.log('[Launch] Backing up node_modules/electron files...');
try {
  if (!fs.existsSync(backupDir)) {
    fs.mkdirSync(backupDir, { recursive: true });
  }

  for (const file of filesToBackup) {
    const src = path.join(electronDir, file);
    const dest = path.join(backupDir, file);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, dest);
    }
  }

  // Also backup node_modules inside electron if it exists
  const electronNodeModules = path.join(electronDir, 'node_modules');
  const backupNodeModules = path.join(backupDir, 'node_modules');
  if (fs.existsSync(electronNodeModules)) {
    fs.cpSync(electronNodeModules, backupNodeModules, { recursive: true });
  }

  console.log('[Launch] Backup complete');
} catch (err) {
  console.error('[Launch] Backup failed:', err.message);
  process.exit(1);
}

// Remove files that cause the module shadowing
console.log('[Launch] Removing electron module files...');
try {
  for (const file of filesToBackup) {
    const filePath = path.join(electronDir, file);
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
  }

  // Remove node_modules inside electron
  const electronNodeModules = path.join(electronDir, 'node_modules');
  if (fs.existsSync(electronNodeModules)) {
    fs.rmSync(electronNodeModules, { recursive: true, force: true });
  }

  console.log('[Launch] Module files removed');
} catch (err) {
  console.error('[Launch] Failed to remove files:', err.message);
  restore();
  process.exit(1);
}

// Launch Electron
console.log('[Launch] Starting Electron...');
const child = spawn(electronExe, ['.'], {
  cwd: __dirname,
  stdio: 'inherit',
  env: {
    ...process.env,
    NODE_ENV: process.env.NODE_ENV || 'production'
  }
});

function restore() {
  console.log('[Launch] Restoring electron module files...');
  try {
    for (const file of filesToBackup) {
      const src = path.join(backupDir, file);
      const dest = path.join(electronDir, file);
      if (fs.existsSync(src)) {
        fs.copyFileSync(src, dest);
      }
    }

    // Restore node_modules
    const backupNodeModules = path.join(backupDir, 'node_modules');
    const electronNodeModules = path.join(electronDir, 'node_modules');
    if (fs.existsSync(backupNodeModules)) {
      fs.cpSync(backupNodeModules, electronNodeModules, { recursive: true });
    }

    console.log('[Launch] Restore complete');
  } catch (err) {
    console.error('[Launch] Restore failed:', err.message);
    console.error('[Launch] You may need to run: npm install electron');
  }
}

child.on('close', (code) => {
  console.log('[Launch] Electron exited with code:', code);
  restore();
  process.exit(code || 0);
});

child.on('error', (err) => {
  console.error('[Launch] Error:', err);
  restore();
  process.exit(1);
});

// Handle Ctrl+C
process.on('SIGINT', () => {
  console.log('[Launch] Received SIGINT, cleaning up...');
  child.kill('SIGINT');
});

process.on('SIGTERM', () => {
  console.log('[Launch] Received SIGTERM, cleaning up...');
  child.kill('SIGTERM');
});
