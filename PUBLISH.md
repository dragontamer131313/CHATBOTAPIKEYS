# Rugged AI publish guide

## Production architecture

Frontend: Netlify. Local inference: supported user browsers via WebGPU. API/control plane: Render. Database: managed PostgreSQL. Distributed controls: Redis. Backups: external S3-compatible storage. Remote model providers are optional fallbacks.

## Render environment
Set `DATABASE_URL` to managed PostgreSQL and `REDIS_URL` to managed Redis. Set `CORS_ORIGINS` to the exact Netlify origin. Keep `JWT_SECRET` and `ADMIN_TOKEN` secret/generated. Leave `PRIMARY_LLM_*` and `BACKUP_LLM_*` empty if you do not use a remote provider.

## Backups
Use `deploy/backup.sh` as a scheduled job/container with AWS credentials and `BACKUP_S3_URI`. Test a restore before launch.

## Developer API keys
Open `/developers.html` on the Netlify site. Developers register/login and create their own `rk_std_...` or `rk_nsfw_...` key. Never share the admin token or database credentials.

## Publish gate
1. Deploy database/Redis.
2. Deploy Render API.
3. Verify `/health`, `/ready`, `/api/capabilities`.
4. Deploy `frontend/` to Netlify.
5. Create an owner API key and test a second account.
6. Test local WebGPU inference on desktop and mobile.
7. Cache a model, disable Wi-Fi, and verify local chat.
8. Test API-key revocation and rate limits.
9. Test backup and restore.
10. Only then share the public URL.
