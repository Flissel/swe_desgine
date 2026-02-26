/**
 * Python Dashboard Server Manager
 *
 * Starts and manages the Python dashboard server as a child process.
 */

import { spawn, ChildProcess } from 'child_process';
import { join } from 'path';

let serverProcess: ChildProcess | null = null;
let serverPort = 8080;
let serverReady = false;

/**
 * Get the project root path
 */
function getProjectRoot(): string {
  // Navigate from dashboard-electron/dist-electron/main to AI-Scientist-v2
  return join(__dirname, '..', '..', '..', '..', '..');
}

/**
 * Start the Python dashboard server
 */
export async function startPythonServer(port: number = 8080): Promise<number> {
  serverPort = port;

  return new Promise((resolve, reject) => {
    const projectRoot = getProjectRoot();

    console.log('[PythonServer] Project root:', projectRoot);
    console.log('[PythonServer] Starting server on port', port);

    // Start the server using Python module
    serverProcess = spawn('python', [
      '-m', 'requirements_engineer.dashboard.server',
      '--port', port.toString(),
      '--no-browser'
    ], {
      cwd: projectRoot,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1'
      },
      shell: true
    });

    if (!serverProcess.stdout || !serverProcess.stderr) {
      reject(new Error('Failed to start Python server'));
      return;
    }

    // Listen for server output
    serverProcess.stdout.on('data', (data: Buffer) => {
      const output = data.toString();
      console.log('[PythonServer]', output);

      if (output.includes('Running on') || output.includes('Started') || output.includes('Serving')) {
        serverReady = true;
        resolve(port);
      }
    });

    serverProcess.stderr.on('data', (data: Buffer) => {
      const error = data.toString();
      console.error('[PythonServer]', error);

      // aiohttp outputs to stderr
      if (error.includes('Running on') || error.includes('Started')) {
        serverReady = true;
        resolve(port);
      }
    });

    serverProcess.on('error', (err) => {
      console.error('[PythonServer] Process error:', err);
      reject(err);
    });

    serverProcess.on('close', (code) => {
      console.log('[PythonServer] Process exited with code', code);
      serverProcess = null;
      serverReady = false;
    });

    // Timeout: resolve after 5 seconds
    setTimeout(() => {
      if (!serverReady) {
        console.log('[PythonServer] Timeout - assuming server ready');
        resolve(port);
      }
    }, 5000);
  });
}

/**
 * Stop the Python server
 */
export function stopPythonServer(): void {
  if (serverProcess) {
    console.log('[PythonServer] Stopping server...');

    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', serverProcess.pid!.toString(), '/f', '/t'], { shell: true });
    } else {
      serverProcess.kill('SIGTERM');
    }

    serverProcess = null;
    serverReady = false;
  }
}

/**
 * Check if server is running
 */
export function isServerRunning(): boolean {
  return serverProcess !== null && serverReady;
}

/**
 * Get server URL
 */
export function getServerUrl(): string {
  return `http://localhost:${serverPort}`;
}
