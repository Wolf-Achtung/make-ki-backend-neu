import { loadSettings } from '/js/settings-store.js';
// Harmonischer Ambient-Sound — startet nur nach Klick auf 'Klang'
let ctx, out, master;
const NOTES = [0, 4, 7, 11, 12]; // kleine Pad-Pentatonik (in Halbtönen ab A)
function noteFreq(semi){ return 220 * Math.pow(2, semi/12); }

function makeVoice(semi, detune=0){
  const o = ctx.createOscillator(); o.type = 'sine'; o.frequency.value = noteFreq(semi); o.detune.value = detune;
  const g = ctx.createGain(); g.gain.value = 0.0;
  const lfo = ctx.createOscillator(); lfo.type='sine'; lfo.frequency.value = 0.15;
  const lfoGain = ctx.createGain(); lfoGain.gain.value = 4;
  lfo.connect(lfoGain).connect(o.detune);
  o.connect(g).connect(out); o.start(); lfo.start();
  return { o, g };
}

function ensure(){
  if (ctx) return;
  ctx = new (window.AudioContext||window.webkitAudioContext)();
  // reverb-ish feedback
  const delay = ctx.createDelay(1.5); delay.delayTime.value = 0.45;
  const fb = ctx.createGain(); fb.gain.value = 0.35; delay.connect(fb).connect(delay);
  const hp = ctx.createBiquadFilter(); hp.type='highpass'; hp.frequency.value = 120;
  out = ctx.createGain(); out.gain.value = (loadSettings()?.volume) ?? 0.08;
  master = ctx.createGain(); master.gain.value = 1.0;
  out.connect(delay).connect(hp).connect(master).connect(ctx.destination);

  // Voices
  const voices = [
    makeVoice(NOTES[0], -4),
    makeVoice(NOTES[2],  3),
    makeVoice(NOTES[4],  0)
  ];
  // gentle fade in
  voices.forEach((v,i)=> v.g.gain.linearRampToValueAtTime(0.10, ctx.currentTime + 0.8 + i*0.2));
}

window.addEventListener('DOMContentLoaded', ()=>{
  const btn = document.getElementById('sound-toggle');
  if (!btn) return;
  btn.addEventListener('click', async ()=>{
    ensure();
    if (ctx.state === 'suspended') { await ctx.resume(); btn.setAttribute('aria-pressed','true'); }
    else if (ctx.state === 'running') { await ctx.suspend(); btn.setAttribute('aria-pressed','false'); }
  }, { passive:true });
});


document.addEventListener('settings-changed', (e)=>{
  if (!ctx || !out) return;
  const v = e.detail?.volume;
  if (typeof v === 'number') {
    out.gain.linearRampToValueAtTime(Math.max(0, Math.min(1, v)), ctx.currentTime + 0.05);
  }
});
