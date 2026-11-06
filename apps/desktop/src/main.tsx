import React from 'react';
import ReactDOM from 'react-dom/client';
// Fonts are bundled locally (offline-first: no CDN). Only the slices actually used get loaded.
import '@fontsource-variable/inter';
import '@fontsource-variable/noto-sans-tc';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
