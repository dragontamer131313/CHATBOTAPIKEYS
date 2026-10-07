# Rugged AI v6 setup

## Architecture

Rugged AI is **local-first**. The browser checks WebGPU and conservative device capabilities, then runs the selected model locally when possible. A Rugged API server is optional fallback.

WebGPU is only available in supported browsers and secure HTTPS contexts, and browser-reported GPU limits are tiered rather than exact VRAM measurements, so automatic model selection is intentionally conservative.

## 1. Publish the frontend

1. Extract this ZIP.
2. Open https://app.netlify.com/drop
3. Drag the `frontend` folder into the Drop zone.
4. Open the generated `netlify.app` address.
5. Connect to the internet on first launch.
6. Press **Download / start local model**.
7. Wait for the model to finish downloading/loading.

The service worker caches the app shell. The local inference engine/browser storage caches the runtime/model data.

## 2. Deploy your Rugged API

Push the complete extracted project to a GitHub repository.

In Render:

1. New -> Web Service.
2. Connect the repository.
3. Choose Docker.
4. Dockerfile: `docker/Dockerfile`.
5. Health check path: `/health`.
6. Deploy.

Set these in Render Environment:

- `JWT_SECRET` — let Render generate it.
- `ADMIN_TOKEN` — let Render generate it.
- `MAX_CONCURRENCY=16`
- `MAX_REQUEST_BYTES=262144`
- `CORS_ORIGINS=https://YOUR-NETLIFY-SITE.netlify.app`

### Provider variables

For local browser inference: **NONE**.

You do not need OpenAI credentials. The old `PRIMARY_LLM_*` variables are only for intentionally configuring a remote OpenAI-compatible inference provider.

## 3. Give yourself and other developers Rugged API keys

After deploying the frontend, open `/developers.html` on your Netlify site. For example: `https://YOUR-SITE.netlify.app/developers.html`. Enter the Render API URL, create/login to an account, and press **Create API key**. Each developer gets their own `rk_std_...` or `rk_nsfw_...` key.

The backend provides:

- `POST /auth/register`
- `POST /auth/login`
- `POST /api/keys`

Developer flow:

1. Create an account.
2. Log in and receive the account JWT.
3. Call `POST /api/keys` using that JWT.
4. The server returns a key such as `rk_std_...` or `rk_nsfw_...`.
5. Use it in your own projects as `Authorization: Bearer rk_...`.

These are **your Rugged API keys**, not OpenAI keys.

For a public developer product, add a developer dashboard for key creation, naming, revocation and rotation.

## Example

```http
POST https://YOUR-RENDER-SERVICE.onrender.com/v1/chat/completions
Authorization: Bearer rk_std_YOUR_KEY
Content-Type: application/json

{
  "model": "rugged-ai",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": false
}
```

## 4. Production performance before many users

For a real multi-user public service, upgrade the data/control plane to:

- PostgreSQL for accounts/conversations instead of SQLite.
- Redis for distributed rate limits, queues and concurrency.
- External object storage for backups.
- Per-key quotas and usage accounting.
- Key revocation/rotation.
- Email verification and password reset.
- Resumable/versioned model downloads.
- A model benchmark on first run, rather than relying only on WebGPU limits.

Keep local browser inference as the preferred path. Use server inference for devices that cannot run the model or when users opt in.

## Offline

Once the web app/runtime/model have been downloaded and cached, local chat can work without Wi-Fi. Cloud-only features such as server fallback, remote sync and server-side memory require connectivity.

## Security

Never share `ADMIN_TOKEN`, `JWT_SECRET`, database credentials or any remote-provider credentials. Developers should receive only their own `rk_std_...` / `rk_nsfw_...` key.
