# Secrets

Nothing in this list is written into Git, the Docker image, or a workflow log on purpose. GitHub masks any value stored as a secret. The workflows pass those values through `env` and do not print them. The EC2 container does not receive access keys. It uses the instance role.

Create each secret in the repository, not in the workflow file.

1. Open the repository on GitHub.
2. Click **Settings**.
3. In the left sidebar, click **Secrets and variables**, then **Actions**.
4. Click **New repository secret**.
5. Paste the name and the value. Click **Add secret**.
6. Repeat for every row below.

| Secret | Where it is used | What to paste |
| --- | --- | --- |
| `DOCKERHUB_USERNAME` | `cd.yml` image name and Docker Hub login | Docker Hub username |
| `DOCKERHUB_TOKEN` | `cd.yml` Docker Hub login | Docker Hub access token, not the account password. Hub → Account Settings → Personal access tokens → Generate. Enable Read and Write on this repository's images |
| `EC2_HOST` | `cd.yml` and `model-release.yml` SSH and the public curl | Public IPv4 or DNS of the instance, without `http://` and without a port |
| `EC2_USER` | SSH user | `ubuntu` on Ubuntu 22.04, `ec2-user` on Amazon Linux 2023 |
| `EC2_SSH_KEY` | SSH private key | Full private key, including the `BEGIN` and `END` lines. Generate it on your laptop: `ssh-keygen -t ed25519 -f ~/.ssh/priceoptima -C priceoptima-deploy`. Do not commit that file |
| `EC2_SSH_FINGERPRINT` | SSH host-key check, so the runner does not trust a new host blindly | After the instance is up: `ssh-keyscan -t ed25519 <EC2_HOST>` then `ssh-keygen -lf` on that output. Paste the `SHA256:...` token |
| `AWS_ROLE_ARN` | Preferred CI credential for `dvc pull` and the commented ECR login. Leave unset if you use access keys instead | ARN of a role whose trust policy allows GitHub OIDC from this repository |
| `AWS_ACCESS_KEY_ID` | CI `dvc pull` and the CD smoke test, only when `AWS_ROLE_ARN` is unset | IAM user key. The EC2 instance must not use this key |
| `AWS_SECRET_ACCESS_KEY` | Same as the access key id | The secret half of that key |
| `AWS_DEFAULT_REGION` | CI, the CD smoke test, and the region string in `.env.prod` if you want them to match | Region of the bucket, `eu-north-1` |

`AWS_ROLE_ARN` and the access-key pair are alternatives. Set the role, or set both key secrets, when CI should `dvc pull` from S3. When neither is present, `pipeline-check` pulls the committed `dvc-storage/` directory and still requires `dvc status` and `dvc repro --dry` to report that the lock is up to date. CD and the EC2 host still expect S3 once you deploy there.

The production environment is a second gate. It is not a secret.

1. In the same **Settings** page, click **Environments**.
2. Click **New environment**. Name it `production`.
3. Tick **Required reviewers** and add yourself.
4. Click **Save protection rules**.

`cd.yml` and `model-release.yml` use `environment: production`. A deploy waits until a reviewer approves it.

## What never goes in a secret or in the image

- Do not put keys in `.env.prod` on the instance. The example file has no keys. `scripts/ec2_bootstrap.sh` copies it to `/opt/priceoptima/.env.prod` and sets mode `600`. A later bootstrap does not overwrite that file.
- Do not `echo` the env file, `docker inspect` the full env list into a log, or run the shell with `set -x` around a secret.
- Do not add a build arg for a token. The Dockerfile copies code, `dvc.lock`, and `.dvc/config`. The config has the remote URL, which is not a credential.
