// File: public/js/settings-store.js
// Simple settings store for model + system prompt with localStorage
export const Settings = {
  get model(){ return localStorage.getItem('model') || ''; },
  set model(v){ localStorage.setItem('model', v || ''); },
  get system(){ return localStorage.getItem('system') || ''; },
  set system(v){ localStorage.setItem('system', v || ''); }
};
