/**
 * Electron Startup Script
 *
 * Workaround for Electron module resolution issue:
 * The npm 'electron' package in node_modules shadows Electron's built-in module.
 * We rename the entire electron folder before spawning so require('electron')
 * falls through to Electron's built-in module.
 */

const path = require('path');
const fs = require('fs');

const isElectron = process.versions && process.versions.electron;
const electronDir = path.join(__dirname, 'node_modules/electron');
const electronDirBackup = path.join(__dirname, 'node_modules/_electron_npm_backup');

if (!isElectron) {
  // === LAUNCHER MODE ===
  const electronExe = path.join(electronDir, 'dist/electron.exe');

  if (!fs.existsSync(electronExe)) {
    console.error('Electron not found at:', electronExe);
    process.exit(1);
  }

  // Copy the electron.exe path before renaming
  const exePath = electronExe;

  // Rename the entire electron folder
  console.log('[Launcher] Temporarily renaming node_modules/electron...');
  try {
    if (fs.existsSync(electronDirBackup)) {
      // Clean up any old backup
      fs.rmSync(electronDirBackup, { recursive: true, force: true });
    }
    fs.renameSync(electronDir, electronDirBackup);
    console.log('[Launcher] Renamed successfully');
  } catch (err) {
    console.error('[Launcher] Failed to rename:', err.message);
    process.exit(1);
  }

  // Spawn Electron - use the new path after rename
  console.log('[Launcher] Starting Electron...');
  const { spawn } = require('child_process');
  const electronExeNew = path.join(electronDirBackup, 'dist/electron.exe');

  const child = spawn(electronExeNew, ['.'], {
    cwd: __dirname,
    stdio: 'inherit'
  });

  child.on('close', (code) => {
    // Restore the folder
    console.log('[Launcher] Restoring node_modules/electron...');
    try {
      if (fs.existsSync(electronDirBackup)) {
        fs.renameSync(electronDirBackup, electronDir);
      }
    } catch (err) {
      console.error('[Launcher] Failed to restore:', err.message);
    }
    process.exit(code || 0);
  });

  child.on('error', (err) => {
    console.error('[Launcher] Error:', err);
    // Restore on error too
    try {
      if (fs.existsSync(electronDirBackup)) {
        fs.renameSync(electronDirBackup, electronDir);
      }
    } catch (e) {
      console.error('[Launcher] Failed to restore:', e.message);
    }
    process.exit(1);
  });

} else {
  // === ELECTRON MAIN PROCESS ===
  console.log('[Main] Running in Electron', process.versions.electron);

  // Debug: check if node_modules/electron exists
  console.log('[Main] Checking electron folder:', fs.existsSync(electronDir) ? 'EXISTS' : 'DOES NOT EXIST');

  // Now require('electron') should use Electron's built-in module
  let electron;
  try {
    electron = require('electron');
    console.log('[Main] require(electron) returned:', typeof electron);
    console.log('[Main] electron.app:', typeof electron.app);
  } catch (e) {
    console.error('[Main] Failed to require electron:', e.message);
    process.exit(1);
  }

  if (!electron.app) {
    console.error('[Main] ERROR: electron.app is undefined!');
    console.error('[Main] electron object keys:', Object.keys(electron));
    process.exit(1);
  }

  const { app, BrowserWindow, ipcMain, dialog, shell } = electron;

  console.log('[Main] Electron API loaded successfully');

  let mainWindow = null;

  function createWindow() {
    mainWindow = new BrowserWindow({
      width: 1600,
      height: 1000,
      minWidth: 1024,
      minHeight: 768,
      webPreferences: {
        preload: path.join(__dirname, 'dist-electron/preload/index.js'),
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: false
      },
      backgroundColor: '#0d1117',
      show: false
    });

    mainWindow.once('ready-to-show', () => {
      mainWindow.show();
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
      shell.openExternal(url);
      return { action: 'deny' };
    });

    const isDev = process.env.NODE_ENV === 'development';
    if (isDev) {
      mainWindow.loadURL('http://localhost:5173');
      mainWindow.webContents.openDevTools();
    } else {
      mainWindow.loadFile(path.join(__dirname, 'dist/index.html'));
    }

    mainWindow.on('closed', () => {
      mainWindow = null;
    });

    console.log('[Main] Window created');
  }

  function registerHandlers() {
    const fsPromises = require('fs').promises;
    const ENTERPRISE_OUTPUT = path.join(process.cwd(), 'enterprise_output');

    ipcMain.handle('projects:list', async () => {
      try {
        if (!fs.existsSync(ENTERPRISE_OUTPUT)) {
          return { success: false, error: `Folder not found: ${ENTERPRISE_OUTPUT}` };
        }
        const entries = await fsPromises.readdir(ENTERPRISE_OUTPUT, { withFileTypes: true });
        const projects = [];
        for (const entry of entries) {
          if (entry.isDirectory()) {
            const projectPath = path.join(ENTERPRISE_OUTPUT, entry.name);
            let nodeCount = 0, diagramCount = 0;
            try {
              const journal = JSON.parse(await fsPromises.readFile(path.join(projectPath, 'journal.json'), 'utf-8'));
              nodeCount = Object.keys(journal.nodes || {}).length;
            } catch {}
            try {
              const diagrams = await fsPromises.readdir(path.join(projectPath, 'diagrams'));
              diagramCount = diagrams.filter(f => f.endsWith('.mmd')).length;
            } catch {}
            projects.push({ name: entry.name, path: projectPath, nodeCount, diagramCount, lastModified: new Date() });
          }
        }
        return { success: true, data: projects };
      } catch (err) {
        return { success: false, error: err.message };
      }
    });

    ipcMain.handle('projects:load', async (_, name) => {
      try {
        const content = await fsPromises.readFile(path.join(ENTERPRISE_OUTPUT, name, 'journal.json'), 'utf-8');
        return { success: true, data: JSON.parse(content) };
      } catch (err) {
        return { success: false, error: err.message };
      }
    });

    ipcMain.handle('diagrams:list', async (_, name) => {
      try {
        const diagramsPath = path.join(ENTERPRISE_OUTPUT, name, 'diagrams');
        const files = await fsPromises.readdir(diagramsPath);
        const diagrams = [];
        for (const file of files.filter(f => f.endsWith('.mmd'))) {
          const code = await fsPromises.readFile(path.join(diagramsPath, file), 'utf-8');
          const match = file.match(/^([A-Z]+-\d+)_(\w+)\.mmd$/);
          diagrams.push({ filename: file, reqId: match?.[1] || file, type: match?.[2] || 'unknown', code });
        }
        return { success: true, data: diagrams };
      } catch (err) {
        return { success: false, error: err.message };
      }
    });

    ipcMain.handle('dialog:selectFolder', async () => {
      const result = await dialog.showOpenDialog({ properties: ['openDirectory'] });
      return result.filePaths[0];
    });

    ipcMain.handle('config:setEnterpriseOutputPath', () => ({ success: true, data: ENTERPRISE_OUTPUT }));
    ipcMain.handle('config:getEnterpriseOutputPath', () => ({ success: true, data: ENTERPRISE_OUTPUT }));

    console.log('[Main] IPC handlers registered');
  }

  app.whenReady().then(() => {
    console.log('[Main] App ready');
    registerHandlers();
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  console.log('[Main] Initialization complete');
}
