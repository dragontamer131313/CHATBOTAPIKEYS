# Rugged AI site setup

The public site is now a simple 3-step key generator:
1. Regular or Adult
2. Server only or Server + offline
3. Get API key

No Rugged account is required.

## Connect Netlify to Render

The site calls `/api/keys/generate` on the same origin by default. The cleanest production setup is a Netlify rewrite/proxy from `/api/*` to the Render API.

If you do not use a Netlify proxy, edit `frontend/config.js` before deploying and set:

```js
window.RUGGED_API_URL = "https://YOUR-RENDER-SERVICE.onrender.com";
```

## Server + offline behavior

The generated key stores its deployment policy. A client can call `/api/model-config` with the key. For `server+offline`, the response includes the compatible local model if one is configured.

`frontend/rugged-client.js` is an optional client helper. It:
- asks Rugged which deployment was selected;
- checks whether WebGPU is available;
- downloads/caches the configured WebLLM model when allowed;
- otherwise uses `/v1/chat/completions` on the server.

A key by itself cannot force an arbitrary third-party website/APK to install a model. The developer must integrate the Rugged client/runtime into that app. On devices without a compatible local runtime, the app falls back to the server.

## Adult offline model

Set `RUGGED_LOCAL_MODEL_ADULT` on Render to a compatible adult-capable model identifier before issuing Adult + Server + offline keys. Without that setting, the API intentionally refuses that combination rather than pretending the regular model is an adult model.

For server model routing, configure:
- `PRIMARY_LLM_MODEL_STANDARD`
- `PRIMARY_LLM_MODEL_ADULT`
- `BACKUP_LLM_MODEL_STANDARD`
- `BACKUP_LLM_MODEL_ADULT`

## What the generated key means

- **Regular + Server only:** the app uses Rugged's server model.
- **Regular + Server + offline:** the integrated client may choose a compatible local model and cache it on the user's device; otherwise it uses the server.
- **Adult + Server only:** Adult requests use the configured adult server model.
- **Adult + Server + offline:** only available after `RUGGED_LOCAL_MODEL_ADULT` is configured.

The key is not a model file and cannot by itself make an arbitrary chatbot install software. The automatic device-aware behavior is implemented by the app's Rugged client integration.
