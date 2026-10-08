# Rugged AI: Netlify + Render

Render is the backend/API. Netlify is the public website.

## Render
1. Deploy the repository to Render as the existing Web Service.
2. Confirm `https://YOUR-RENDER-URL/health` returns JSON with `ok: true`.
3. The root URL should now return API information instead of a 404.
4. Configure at least one model provider in Render:
   - PRIMARY_LLM_BASE_URL
   - PRIMARY_LLM_API_KEY
   - PRIMARY_LLM_MODEL
   - optional BACKUP_LLM_BASE_URL / BACKUP_LLM_API_KEY / BACKUP_LLM_MODEL

The API does not contain model weights itself. It needs a reachable OpenAI-compatible model server/provider unless a local model server is added.

## Netlify
1. Create/open your Netlify site.
2. Connect it to the same GitHub repository.
3. Set the publish directory to `frontend` (the included `netlify.toml` already does this).
4. Deploy.
5. Open your Netlify URL.
6. Open **Developer Portal** and enter your Render URL, for example:
   `https://your-service.onrender.com`
7. Generate a key. The full secret is shown only once.

The frontend can call Render directly because the API currently permits CORS. If you later want a same-domain `/api` proxy, put your real Render URL into the commented Netlify rewrite rules and redeploy.

## Key generation
`POST /api/keys/generate` creates a key without a Rugged account. The database stores only a SHA-256 hash of the secret. Anonymous generation is rate limited.
