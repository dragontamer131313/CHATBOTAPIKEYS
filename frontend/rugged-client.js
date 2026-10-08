/* Rugged Client: optional helper for apps that offer Server + offline mode.
   It reads the deployment policy from the API key, detects WebGPU, and loads
   a compatible WebLLM model when the key permits offline mode. */
export async function createRuggedClient({ apiKey, apiBase, webllmImport = 'https://esm.run/@mlc-ai/web-llm' }) {
  const base=(apiBase||'').replace(/\/$/,'');
  if(!apiKey) throw new Error('Rugged API key is required');
  const headers={Authorization:`Bearer ${apiKey}`};
  const cfgRes=await fetch(`${base}/api/model-config`,{headers});
  if(!cfgRes.ok) throw new Error(await cfgRes.text());
  const config=await cfgRes.json();
  let local=null;
  if(config.offline && config.local?.enabled && config.local?.model && navigator.gpu){
    try{
      const adapter=await navigator.gpu.requestAdapter();
      if(adapter){
        const webllm=await import(webllmImport);
        local=await webllm.CreateMLCEngine(config.local.model);
      }
    }catch(_){ local=null; }
  }
  return {
    config,
    local,
    async chat(messages, options={}){
      if(local) return local.chat.completions.create({messages,...options});
      const r=await fetch(`${base}/v1/chat/completions`,{method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({messages,content_mode:config.profile==='adult'?'adult':'general',...options})});
      if(!r.ok) throw new Error(await r.text());
      return r.json();
    }
  };
}
