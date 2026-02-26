/**
 * RE System Dashboard - Electron Main Process
 *
 * Launches the Python dashboard server as a subprocess and displays
 * the web-based dashboard in an Electron window.
 *
 * Features:
 * - Automatic port detection
 * - Python subprocess management
 * - Graceful shutdown
 * - Dev tools toggle with --dev flag
 */

const { app, BrowserWindow, ipcMain, dialog, Menu } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const net = require('net');

// Configuration
const DEFAULT_PORT = 8085;
// On Windows use 'py' (Python Launcher), on Unix use 'python3'
const PYTHON_COMMAND = process.platform === 'win32' ? 'py' : 'python3';
const SERVER_STARTUP_TIMEOUT = 30000; // 30 seconds

// Parse CLI args: --project <path> --config <path>
function parseArgs() {
    const args = process.argv.slice(1); // skip electron binary
    const result = { project: null, config: 're_config.yaml' };
    for (let i = 0; i < args.length; i++) {
        if ((args[i] === '--project' || args[i] === '-p') && args[i + 1]) {
            result.project = args[++i];
        } else if ((args[i] === '--config' || args[i] === '-c') && args[i + 1]) {
            result.config = args[++i];
        }
    }
    return result;
}
const cliArgs = parseArgs();

// State
let mainWindow = null;
let pythonProcess = null;
let serverPort = DEFAULT_PORT;
let isQuitting = false;

/**
 * Find an available port starting from the given port.
 */
async function findAvailablePort(startPort) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.listen(startPort, '127.0.0.1', () => {
            const port = server.address().port;
            server.close(() => resolve(port));
        });
        server.on('error', () => resolve(findAvailablePort(startPort + 1)));
    });
}

/**
 * Wait for the Python server to become available.
 */
async function waitForServer(port, timeout = SERVER_STARTUP_TIMEOUT) {
    const startTime = Date.now();
    while (Date.now() - startTime < timeout) {
        try {
            const response = await fetch(`http://localhost:${port}/api/state`);
            if (response.ok) {
                return true;
            }
        } catch (e) {
            // Server not ready yet
        }
        await new Promise(r => setTimeout(r, 500));
    }
    throw new Error(`Server startup timeout after ${timeout}ms`);
}

/**
 * Start the Python dashboard server.
 */
async function startPythonServer() {
    serverPort = await findAvailablePort(DEFAULT_PORT);
    const projectRoot = path.resolve(__dirname, '..', '..');

    console.log(`[Electron] Starting Python server on port ${serverPort}...`);
    console.log(`[Electron] Project root: ${projectRoot}`);

    const pyArgs = [
        '-m', 'requirements_engineer.dashboard',
        '--port', serverPort.toString(),
        '--no-browser'
    ];

    // Forward --project and --config to Python
    if (cliArgs.project) {
        const absProject = path.resolve(cliArgs.project);
        pyArgs.push('--project', absProject);
        console.log(`[Electron] Pipeline auto-start: ${absProject}`);
    }
    if (cliArgs.config) {
        pyArgs.push('--config', cliArgs.config);
    }

    pythonProcess = spawn(PYTHON_COMMAND, pyArgs, {
        cwd: projectRoot,
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
        stdio: ['ignore', 'pipe', 'pipe']
    });

    // Log stdout
    pythonProcess.stdout.on('data', (data) => {
        const msg = data.toString().trim();
        console.log(`[Python] ${msg}`);
        if (mainWindow) {
            mainWindow.webContents.send('server:log', { level: 'info', message: msg });
        }
    });

    // Log stderr
    pythonProcess.stderr.on('data', (data) => {
        const msg = data.toString().trim();
        console.error(`[Python] ${msg}`);
        if (mainWindow) {
            mainWindow.webContents.send('server:log', { level: 'error', message: msg });
        }
    });

    // Handle exit
    pythonProcess.on('exit', (code) => {
        console.log(`[Python] Server exited with code ${code}`);
        if (!isQuitting && code !== 0) {
            dialog.showErrorBox('Server Crashed', `Python server exited with code ${code}`);
        }
    });

    pythonProcess.on('error', (err) => {
        console.error(`[Python] Failed to start: ${err.message}`);
        dialog.showErrorBox('Server Error', `Failed to start Python server: ${err.message}`);
    });

    // Wait for server to be ready
    await waitForServer(serverPort);
    console.log(`[Electron] Server ready on port ${serverPort}`);

    return serverPort;
}

/**
 * Stop the Python server.
 */
function stopPythonServer() {
    if (pythonProcess) {
        console.log('[Electron] Stopping Python server...');
        if (process.platform === 'win32') {
            // Windows: Use taskkill to kill the process tree
            exec(`taskkill /pid ${pythonProcess.pid} /T /F`, (err) => {
                if (err) console.error('[Electron] taskkill error:', err);
            });
        } else {
            pythonProcess.kill('SIGTERM');
        }
        pythonProcess = null;
    }
}

/**
 * Create the main application window.
 */
function createWindow(port) {
    mainWindow = new BrowserWindow({
        width: 1600,
        height: 1000,
        minWidth: 1200,
        minHeight: 800,
        backgroundColor: '#0a0a0a',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        title: 'RE System Dashboard',
        icon: path.join(__dirname, 'icon.png'),
        show: false
    });

    // Load the dashboard
    mainWindow.loadURL(`http://localhost:${port}`);

    // Show window when ready
    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        if (process.argv.includes('--dev')) {
            mainWindow.webContents.openDevTools();
        }
    });

    // Handle window close
    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // Create application menu
    createMenu();
}

/**
 * Create the application menu.
 */
function createMenu() {
    const template = [
        {
            label: 'File',
            submenu: [
                {
                    label: 'Run Pipeline...',
                    accelerator: 'CmdOrCtrl+O',
                    click: async () => {
                        const result = await dialog.showOpenDialog(mainWindow, {
                            title: 'Select Project JSON(s) — multi-select with Ctrl/Shift',
                            defaultPath: path.resolve(__dirname, '..', '..', 're_ideas'),
                            filters: [
                                { name: 'Project JSON', extensions: ['json'] },
                                { name: 'All Files', extensions: ['*'] }
                            ],
                            properties: ['openFile', 'multiSelections']
                        });
                        if (result.canceled || !result.filePaths.length) return;
                        const projects = result.filePaths;
                        try {
                            const endpoint = projects.length === 1
                                ? '/api/pipeline/run'
                                : '/api/pipeline/batch';
                            const body = projects.length === 1
                                ? { project_path: projects[0] }
                                : { projects };
                            const resp = await fetch(`http://localhost:${serverPort}${endpoint}`, {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify(body)
                            });
                            const data = await resp.json();
                            if (data.error) {
                                dialog.showErrorBox('Pipeline Error', data.error);
                            } else {
                                const count = data.projects || 1;
                                console.log(`[Electron] Pipeline started for ${count} project(s)`);
                            }
                        } catch (err) {
                            dialog.showErrorBox('Pipeline Error', err.message);
                        }
                    }
                },
                {
                    label: 'Stop Pipeline',
                    click: async () => {
                        try {
                            await fetch(`http://localhost:${serverPort}/api/pipeline/stop`, { method: 'POST' });
                        } catch (err) {
                            // Server may not be running
                        }
                    }
                },
                { type: 'separator' },
                { role: 'quit' }
            ]
        },
        {
            label: 'View',
            submenu: [
                { role: 'reload' },
                { role: 'forceReload' },
                { type: 'separator' },
                { role: 'toggleDevTools' },
                { type: 'separator' },
                { role: 'resetZoom' },
                { role: 'zoomIn' },
                { role: 'zoomOut' },
                { type: 'separator' },
                { role: 'togglefullscreen' }
            ]
        },
        {
            label: 'Layout',
            submenu: [
                {
                    label: 'Cluster',
                    click: () => {
                        if (mainWindow) {
                            mainWindow.webContents.send('menu:layout', 'by_cluster');
                        }
                    }
                },
                {
                    label: 'Hierarchy',
                    click: () => {
                        if (mainWindow) {
                            mainWindow.webContents.send('menu:layout', 'by_hierarchy');
                        }
                    }
                },
                {
                    label: 'Matrix',
                    click: () => {
                        if (mainWindow) {
                            mainWindow.webContents.send('menu:layout', 'by_matrix');
                        }
                    }
                }
            ]
        },
        {
            label: 'Server',
            submenu: [
                {
                    label: 'Restart Server',
                    click: async () => {
                        stopPythonServer();
                        try {
                            const port = await startPythonServer();
                            if (mainWindow) {
                                mainWindow.loadURL(`http://localhost:${port}`);
                            }
                        } catch (err) {
                            dialog.showErrorBox('Server Error', err.message);
                        }
                    }
                },
                {
                    label: 'Open in Browser',
                    click: () => {
                        require('electron').shell.openExternal(`http://localhost:${serverPort}`);
                    }
                }
            ]
        },
        {
            label: 'Help',
            submenu: [
                {
                    label: 'About',
                    click: () => {
                        dialog.showMessageBox({
                            type: 'info',
                            title: 'About RE System Dashboard',
                            message: 'RE System Dashboard v1.0.0',
                            detail: 'Requirements Engineering System with Matrix Visualization\n\nPowered by Sakana AI'
                        });
                    }
                }
            ]
        }
    ];

    const menu = Menu.buildFromTemplate(template);
    Menu.setApplicationMenu(menu);
}

// ============================================
// App Lifecycle
// ============================================

app.whenReady().then(async () => {
    // Register IPC handlers
    ipcMain.handle('server:get-port', () => serverPort);

    ipcMain.handle('server:get-status', () => ({
        running: !!pythonProcess,
        port: serverPort
    }));

    ipcMain.handle('server:restart', async () => {
        stopPythonServer();
        try {
            const port = await startPythonServer();
            if (mainWindow) {
                mainWindow.loadURL(`http://localhost:${port}`);
            }
            return { success: true, port };
        } catch (err) {
            return { success: false, error: err.message };
        }
    });

    // Start the server and create window
    try {
        const port = await startPythonServer();
        createWindow(port);
    } catch (error) {
        dialog.showErrorBox('Startup Error', error.message);
        app.quit();
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (mainWindow === null) {
        startPythonServer()
            .then(port => createWindow(port))
            .catch(err => dialog.showErrorBox('Error', err.message));
    }
});

app.on('before-quit', () => {
    isQuitting = true;
    stopPythonServer();
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
    console.error('[Electron] Uncaught exception:', error);
    stopPythonServer();
});
