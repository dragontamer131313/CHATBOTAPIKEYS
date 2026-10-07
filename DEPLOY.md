# PUBLIC DEPLOYMENT

## Netlify Drop
1. Extract the ZIP.
2. Go to https://app.netlify.com/drop
3. Drag the `frontend` folder into the Drop zone.
4. Copy the resulting `https://....netlify.app` address.
5. The frontend's API URL field can point to your Render API.

## Render
1. Create a GitHub repository and upload the whole project.
2. In Render: New -> Web Service -> connect the GitHub repo.
3. Choose Docker.
4. Dockerfile: `docker/Dockerfile`.
5. Health check: `/health`.
6. Add the variables shown in `render.yaml`.
7. Deploy.
8. Copy the resulting `https://....onrender.com` URL.
9. Put that URL into the Netlify site's API URL.

Never put ADMIN_TOKEN, JWT_SECRET, or model-provider secrets in Netlify frontend code.

## Reliability
The API has a bounded request semaphore, two attempts per provider, exponential-ish backoff, and primary->backup provider failover. Render health checks can restart unhealthy instances.

## Backups
The prototype has `/admin/backup`. For serious production, use PostgreSQL with automated managed backups and object storage; do not rely on a local Render filesystem as the only copy.
