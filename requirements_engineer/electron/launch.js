#!/usr/bin/env node
/**
 * Electron launcher that strips ELECTRON_RUN_AS_NODE.
 *
 * VSCode (an Electron app itself) sets ELECTRON_RUN_AS_NODE=1 in its
 * integrated terminal.  This makes any nested Electron process behave
 * as plain Node.js, breaking `require('electron')`.
 *
 * This tiny wrapper removes the variable before spawning the real
 * Electron binary so `npm start` works from any terminal.
 */

delete process.env.ELECTRON_RUN_AS_NODE;

const electron = require('electron');
const { spawn } = require('child_process');

const child = spawn(electron, ['.', ...process.argv.slice(2)], {
    stdio: 'inherit',
    windowsHide: false,
    env: process.env              // ELECTRON_RUN_AS_NODE is already removed
});

child.on('close', (code) => process.exit(code ?? 1));

['SIGINT', 'SIGTERM'].forEach(sig =>
    process.on(sig, () => { if (!child.killed) child.kill(sig); })
);
