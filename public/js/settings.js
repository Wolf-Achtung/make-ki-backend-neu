
const KEY = 'hohl_settings';
function defaults(){
  return {
    apiBase: (document.querySelector('meta[name="hohl-chat-base"]')?.content || '').trim(),
    model: '',
    systemPrompt: '',
    temperature: 0.7,
    maxTokens: 1024
  };
}
export const settings = new Proxy({ ...defaults(), ...JSON.parse(localStorage.getItem(KEY) || '{}') }, {
  set(target, prop, value){ target[prop] = value; localStorage.setItem(KEY, JSON.stringify(target)); return true; }
});
export function saveSettings(obj){ Object.assign(settings, obj || {}); }
