/**
 * RE System Dashboard - Embeddable Module
 *
 * Allows embedding the RE Dashboard into other Electron applications
 * using BrowserView.
 *
 * Usage in parent Electron app:
 *
 *   const { startREServer, stopREServer, createREDashboardView } = require('./embed');
 *
 *   // Start the server
 *   const port = await startREServer();
 *
 *   // Create a view in your main window
 *   const view = createREDashboardView(mainWindow, port, {
 *     bounds: { x: 300, y: 0, width: 1200, height: 800 }
 *   });
 *
 *   // Clean up when done
 *   stopREServer();
 */

const { BrowserView } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const net = require('net');

// Configuration
const DEFAULT_PORT = 8085;
// On Windows use 'py' (Python Launcher), on Unix use 'python3'
const PYTHON_COMMAND = process.platform === 'win32' ? 'py' : 'python3';

// State
let pythonProcess = null;
let currentPort = null;

/**
 * Find an available port starting from the given port.
 */
async function findAvailablePort(startPort = DEFAULT_PORT) {
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
 * Wait for the server to become available.
 */
async function waitForServer(port, timeout = 30000) {
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
 * Start the RE Dashboard Python server.
 *
 * @param {Object} options - Configuration options
 * @param {string} options.pythonPath - Path to Python executable (default: 'python' or 'python3')
 * @param {string} options.projectRoot - Path to AI-Scientist-v2 project root
 * @param {number} options.port - Preferred port (will find next available if taken)
 * @returns {Promise<number>} The port the server is running on
 */
async function startREServer(options = {}) {
    const {
        pythonPath = PYTHON_COMMAND,
        projectRoot = path.resolve(__dirname, '..', '..'),
        port = DEFAULT_PORT
    } = options;

    // Find available port
    currentPort = await findAvailablePort(port);

    console.log(`[RE-Embed] Starting server on port ${currentPort}...`);

    pythonProcess = spawn(pythonPath, [
        '-m', 'requirements_engineer.dashboard',
        '--port', currentPort.toString(),
        '--no-browser'
    ], {
        cwd: projectRoot,
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
        stdio: ['ignore', 'pipe', 'pipe']
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[RE-Server] ${data.toString().trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[RE-Server] ${data.toString().trim()}`);
    });

    pythonProcess.on('exit', (code) => {
        console.log(`[RE-Server] Exited with code ${code}`);
    });

    // Wait for server to be ready
    await waitForServer(currentPort);
    console.log(`[RE-Embed] Server ready on port ${currentPort}`);

    return currentPort;
}

/**
 * Stop the RE Dashboard Python server.
 */
function stopREServer() {
    if (pythonProcess) {
        console.log('[RE-Embed] Stopping server...');
        if (process.platform === 'win32') {
            exec(`taskkill /pid ${pythonProcess.pid} /T /F`);
        } else {
            pythonProcess.kill('SIGTERM');
        }
        pythonProcess = null;
        currentPort = null;
    }
}

/**
 * Get the current server port.
 *
 * @returns {number|null} The current port or null if not running
 */
function getServerPort() {
    return currentPort;
}

/**
 * Check if the server is running.
 *
 * @returns {boolean} True if the server is running
 */
function isServerRunning() {
    return pythonProcess !== null && currentPort !== null;
}

/**
 * Create a BrowserView for the RE Dashboard.
 *
 * @param {BrowserWindow} parentWindow - The parent Electron window
 * @param {number} port - The port the server is running on
 * @param {Object} options - View options
 * @param {Object} options.bounds - View bounds { x, y, width, height }
 * @param {boolean} options.autoResize - Whether to auto-resize with parent
 * @returns {BrowserView} The created BrowserView
 */
function createREDashboardView(parentWindow, port, options = {}) {
    const {
        bounds = { x: 0, y: 0, width: 800, height: 600 },
        autoResize = true
    } = options;

    const view = new BrowserView({
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        }
    });

    parentWindow.setBrowserView(view);
    view.setBounds(bounds);

    if (autoResize) {
        view.setAutoResize({
            width: true,
            height: true,
            horizontal: false,
            vertical: false
        });
    }

    view.webContents.loadURL(`http://localhost:${port}`);

    return view;
}

/**
 * Remove a BrowserView from its parent window.
 *
 * @param {BrowserWindow} parentWindow - The parent window
 * @param {BrowserView} view - The view to remove
 */
function removeREDashboardView(parentWindow, view) {
    if (parentWindow && view) {
        parentWindow.removeBrowserView(view);
    }
}

// Export functions
module.exports = {
    startREServer,
    stopREServer,
    getServerPort,
    isServerRunning,
    createREDashboardView,
    removeREDashboardView
};
