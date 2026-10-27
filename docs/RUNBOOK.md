# Runbook

The host directory is `/opt/priceoptima`. The git checkout is `/opt/priceoptima/src`. The env file is `/opt/priceoptima/.env.prod` and is not inside the checkout. `current.env` and `previous.env` record the image and the model pin.

## Deploy code

A push to `main` runs CI. When CI is green, CD builds the image, smoke-tests it, scans it, pushes it, and waits for the `production` environment. Approve the deployment in the Actions tab. CD SSHes to the instance and runs `scripts/deploy.sh` with the short SHA tag.

To deploy by hand:

```bash
ssh -i ~/.ssh/priceoptima ubuntu@<EC2_HOST>
cd /opt/priceoptima/src
git fetch origin
git checkout --force origin/main
bash scripts/deploy.sh <dockerhub-user>/priceoptima:<short-sha>
```

`deploy.sh` pulls the image, remembers the running image, starts the new one with `--restart unless-stopped`, and curls `http://127.0.0.1:8000/ready` for up to 120 seconds. The model pin already on the container is kept, so a code deploy does not change `MODEL_VERSION`.

## Roll back code

If `/ready` does not succeed, `deploy.sh` starts the previous image and exits non-zero. CD also curls the public `/ready` and `/model-info` for 120 seconds. If that fails, it runs `deploy.sh` again with the image in `/opt/priceoptima/previous.env`.

By hand:

```bash
prev="$(sed -n 's/^image=//p' /opt/priceoptima/previous.env | head -1)"
bash /opt/priceoptima/src/scripts/deploy.sh "$prev"
```

The result file is `/opt/priceoptima/deploy_result`. `status=rolled_back` means the new tag was rejected and the previous tag is serving.

## Roll back the model

This does not build or pull a different image.

GitHub: **Actions**, **Model release**, **Run workflow**, input `model-v1` or `model-v2`. Approve `production`. The workflow runs `scripts/roll_model.sh`, which restarts the current image with `MODEL_VERSION` set. `/model-info` then shows that version. If it does not become ready in 120 seconds, the workflow starts the previous image and the previous pin.

On the host:

```bash
bash /opt/priceoptima/src/scripts/roll_model.sh model-v1
curl -fsS http://127.0.0.1:8000/model-info
```

## Logs and the restart policy

```bash
docker logs --tail 100 priceoptima
docker ps --filter name=priceoptima
docker inspect -f '{{.HostConfig.RestartPolicy.Name}} {{.RestartCount}}' priceoptima
```

`unless-stopped` means Docker starts the container after a daemon restart or a reboot, and after the process exits. It does not start a container you stopped with `docker stop` or `docker kill`. `RestartCount` increases when the process dies and Docker brings it back.

JSON request lines are on stdout: `request_id`, `endpoint`, `status`, `latency_ms`. The model fetch lines are there too. They do not include AWS keys.

## Health cron

```bash
crontab -e
```

Add:

```
*/5 * * * * /opt/priceoptima/src/scripts/healthcheck.sh
```

The script appends one line to `/opt/priceoptima/health.log` and exits non-zero when `/ready` is not 200. Read it with `tail -n 20 /opt/priceoptima/health.log`.

## Rotate secrets

1. Docker Hub: create a new access token, update `DOCKERHUB_TOKEN`, delete the old token in Hub.
2. GitHub SSH key: generate a new ed25519 key, append the public key to `~/.ssh/authorized_keys` on the instance, update `EC2_SSH_KEY`, then remove the old public-key line.
3. Host fingerprint: only changes when the instance or its SSH host keys are replaced. Update `EC2_SSH_FINGERPRINT` from a fresh `ssh-keyscan`.
4. AWS CI keys, if you are not using the OIDC role: create a new access key, update both GitHub secrets, delete the old key in IAM. Do not copy the new key into `.env.prod`.
5. Instance role: edit `PriceOptimaDvcRead` in IAM. No file on the instance changes. The next `dvc pull` uses the updated policy.

After a rotation, re-run the workflow that uses that secret. Do not print the new value to confirm it.

## Stop the bill

EC2 console → select the instance → **Instance state** → **Stop instance**. See `docs/EC2_SETUP.md` for the Elastic IP note. Starting it again can change the public IP. Update `EC2_HOST` and re-check the fingerprint before the next deploy.
