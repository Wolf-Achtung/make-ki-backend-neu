// File: server/utils/sse.js
// Minimal Server-Sent Events line parser
export function* parseSSE(textChunk) {
  // Accepts text block(s), yields { event, data }
  const lines = textChunk.split(/\r?\n/);
  let event = 'message';
  for (const line of lines) {
    if (!line) { continue; }
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      let data = line.slice(5).trim();
      yield { event, data };
      event = 'message';
    }
  }
}
