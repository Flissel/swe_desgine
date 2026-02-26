/**
 * Renderer Entry Point
 *
 * Initializes React and mounts the App component.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

// Ensure root element exists
const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Root element not found. Check index.html has <div id="root"></div>');
}

// Create React root and render
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

// Log startup info
console.log('[Renderer] Dashboard started');
console.log('[Renderer] API available:', typeof window.api !== 'undefined');
