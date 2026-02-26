/**
 * Electron Main Process
 *
 * Starts the Python dashboard server and loads the full dashboard UI.
 */

import { app, BrowserWindow, shell } from 'electron';
import { join } from 'path';
import { registerFileSystemHandlers } from './ipc/fileSystem';
import { startPythonServer, stopPythonServer, getServerUrl } from './pythonServer';

// Handle Squirrel startup (optional - only for Squirrel installer)
try {
  if (require.resolve('electron-squirrel-startup')) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    if (require('electron-squirrel-startup')) {
      app.quit();
    }
  }
} catch {
  // electron-squirrel-startup not installed
}

let mainWindow: BrowserWindow | null = null;
const DASHBOARD_PORT = 8080;

async function createWindow() {
  // Create the browser window
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1024,
    minHeight: 768,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false,
      webSecurity: false  // Allow loading local resources
    },
    backgroundColor: '#0d1117',
    show: false,
    title: 'RE System Dashboard'
  });

  // Show window when ready
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // Open external links in browser
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://localhost:')) {
      return { action: 'allow' };
    }
    shell.openExternal(url);
    return { action: 'deny' };
  });

  // Load the Python dashboard
  const dashboardUrl = getServerUrl();
  console.log('[Electron] Loading dashboard from:', dashboardUrl);

  try {
    await mainWindow.loadURL(dashboardUrl);
  } catch (err) {
    console.error('[Electron] Failed to load dashboard:', err);
    // Show error page
    mainWindow.loadURL(`data:text/html,
      <html>
        <head><style>
          body { background: #0d1117; color: #c9d1d9; font-family: system-ui; padding: 40px; }
          h1 { color: #f85149; }
          pre { background: #161b22; padding: 20px; border-radius: 8px; }
        </style></head>
        <body>
          <h1>❌ Dashboard Server nicht erreichbar</h1>
          <p>Der Python-Server konnte nicht gestartet werden.</p>
          <pre>URL: ${dashboardUrl}\n\nBitte stelle sicher dass Python installiert ist und die Dependencies vorhanden sind.</pre>
          <p>Versuche: <code>pip install aiohttp</code></p>
        </body>
      </html>
    `);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// App ready
app.whenReady().then(async () => {
  console.log('[Electron] App ready, starting Python server...');

  // Register IPC handlers
  registerFileSystemHandlers();

  // Start Python dashboard server
  try {
    await startPythonServer(DASHBOARD_PORT);
    console.log('[Electron] Python server started');
  } catch (err) {
    console.error('[Electron] Failed to start Python server:', err);
  }

  // Create window
  await createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit handler
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Cleanup on quit
app.on('will-quit', () => {
  console.log('[Electron] Stopping Python server...');
  stopPythonServer();
});

// Allow navigation to localhost
app.on('web-contents-created', (_, contents) => {
  contents.on('will-navigate', (event, navigationUrl) => {
    const parsedUrl = new URL(navigationUrl);
    // Allow localhost navigation
    if (parsedUrl.hostname === 'localhost' || parsedUrl.hostname === '127.0.0.1') {
      return;
    }
    event.preventDefault();
  });
});
