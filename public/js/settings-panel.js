
const DEFAULT_MODELS = [
  { id: 'claude-3-5-sonnet-20240620', display: 'Claude 3.5 Sonnet' },
  { id: 'claude-3-haiku-20240307', display: 'Claude 3 Haiku' }
];
import { settings, saveSettings } from './settings.js';
import { t, lang, setLang } from './i18n.js';
import { sfx } from './sfx.js';
const root = document.getElementById('popup-root');
const nav = document.getElementById('nav');
function el(tag, attrs={}, children=[]){ const e=document.createElement(tag); Object.entries(attrs).forEach(([k,v])=>{ if(k==='text') e.textContent=v; else if(k==='html') e.innerHTML=v; else e.setAttribute(k,v); }); children.forEach(c=>e.appendChild(c)); return e; }
function openPanel(){
  sfx.nav();
  const wrap=el('div',{class:'popup'}); const inner=el('div',{class:'popup-inner'});
  const head=el('div',{class:'popup-header'},[ el('h3',{text:t('settings')}), (()=>{const b=el('button',{class:'btn btn-secondary',text:t('close')}); b.onclick=()=>wrap.remove(); return b;})() ]);
  const body=el('div',{class:'popup-body'});
  const langRow=el('div',{},[ el('label',{for:'set-lang',text:t('language')}), (()=>{const s=el('select',{id:'set-lang'}); ['de','en'].forEach(l=>{ const o=el('option',{value:l,text:l.toUpperCase()}); if(l===lang()) o.selected=true; s.appendChild(o); }); s.onchange=()=>setLang(s.value); return s; })() ]);
  const modelRow=el('div',{},[ el('label',{for:'set-model',text:t('model')}), (()=>{const s=el('select',{id:'set-model'}); fetch('/api/models').then(r=>r.ok?r.json():Promise.reject(new Error('HTTP '+r.status))).then(list=>(list.models||list||DEFAULT_MODELS).forEach(m=>{const o=document.createElement('option'); o.value=m.id||m.name||m; o.textContent=m.display||m.id||m.name||m; s.appendChild(o);})).catch(()=>DEFAULT_MODELS.forEach(m=>{const o=document.createElement('option'); o.value=m.id; o.textContent=m.display; s.appendChild(o);})); return s; })() ]);
  const sysRow=el('div',{},[ el('label',{for:'set-system',text:t('system_prompt')}), el('textarea',{id:'set-system'}) ]);
  const tempRow=el('div',{},[ el('label',{for:'set-temp',text:t('temperature')}), (()=>{const i=el('input',{id:'set-temp',type:'number',step:'0.1',min:'0',max:'2'}); i.value=String(settings.temperature??0.7); return i; })() ]);
  const tokRow=el('div',{},[ el('label',{for:'set-tok',text:t('maxtokens')}), (()=>{const i=el('input',{id:'set-tok',type:'number',step:'1',min:'1',max:'8000'}); i.value=String(settings.maxTokens||1024); return i; })() ]);
  const apiRow=el('div',{},[ el('label',{for:'set-api',text:t('api_base')}), (()=>{const i=el('input',{id:'set-api',type:'text'}); i.value=settings.apiBase||''; return i; })() ]);
  const save=el('button',{class:'btn btn-primary',text:t('save')}); save.onclick=()=>{ saveSettings({ model:document.getElementById('set-model').value, systemPrompt:document.getElementById('set-system').value, temperature:Number(document.getElementById('set-temp').value), maxTokens:Number(document.getElementById('set-tok').value), apiBase:(document.getElementById('set-api').value||'').trim() }); sfx.nav(); wrap.remove(); };
  body.append(langRow,modelRow,sysRow,tempRow,tokRow,apiRow); const actions=el('div',{class:'popup-actions'},[save]); inner.append(head,body,actions); wrap.append(inner); root.append(wrap);
  document.getElementById('set-system').value = settings.systemPrompt || '';
}
nav.addEventListener('click', (ev) => { const btn=ev.target.closest('.nav-btn'); if(!btn) return; const action=btn.getAttribute('data-action'); if(action==='settings') openPanel(); });
document.getElementById('lang-toggle')?.addEventListener('click',()=>{ const l=localStorage.getItem('hohl_lang')==='de'?'en':'de'; setLang(l); });
