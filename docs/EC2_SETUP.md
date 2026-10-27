# EC2 setup

One small instance runs the container. The container pulls `models/model.pkl` from S3 when it starts. The instance role is the only AWS credential on that machine.

Do these console steps once. The scripts in this repo do the repeatable part.

## 1. Push the model to S3 before the first deploy

The committed default remote is `dvc-storage/` in this repository (`.dvc/config` stores `../dvc-storage`). CI uses that directory when no AWS secret is set, and uses the remote named `s3` (`s3://priceoptima/priceoptima`) when `AWS_ROLE_ARN` or `AWS_ACCESS_KEY_ID` is set. EC2 always uses `s3`. Change that URL if your bucket name is different, then commit the config. Do not commit credentials.

From a laptop that already has the local cache:

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="ap-south-1"
dvc push -r s3
```

Confirm both model hashes are present. `model-v1` is gradient boosting (`39e2102397c95cc0022aa2a486414d87`) and `model-v2` is ridge (`cf8a5fc16b1199e1f61f8fc21ad006e2`). `dvc push` adds objects. It does not delete the previous hash.

## 2. IAM role for the instance

1. Open the AWS console and search for **IAM**.
2. Click **Policies**, then **Create policy**.
3. Open the **JSON** tab and paste the policy below. Replace `YOUR_BUCKET` with the bucket in `.dvc/config`.
4. Click **Next**. Name the policy `PriceOptimaDvcRead`. Click **Create policy**.
5. Click **Roles**, then **Create role**.
6. Trusted entity: **AWS service**. Use case: **EC2**. Click **Next**.
7. Search for `PriceOptimaDvcRead`, tick it, click **Next**.
8. Name the role `PriceOptimaEc2`. Click **Create role**.

This is read-only. The instance can pull the model. It cannot push a new one or delete the remote.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListDvcPrefix",
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET",
      "Condition": {
        "StringLike": { "s3:prefix": ["priceoptima", "priceoptima/*"] }
      }
    },
    {
      "Sid": "ReadDvcObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/priceoptima/*"
    }
  ]
}
```

`GetBucketLocation` has no prefix condition that is useful, so if IAM rejects the condition on that action, split it into its own statement without the `StringLike` block. `ListBucket` keeps the prefix condition.

## 3. Launch the instance

1. Open **EC2**, then **Launch instance**.
2. Name it `priceoptima`.
3. Application: **Ubuntu Server 22.04** or **Amazon Linux 2023**. Both are handled by `scripts/ec2_bootstrap.sh`.
4. Instance type: **t3.micro** or **t2.micro** (free tier where your account still has it).
5. Key pair: create or select one so you can SSH yourself. This key is not `EC2_SSH_KEY`. That secret is a second key used only by GitHub Actions, created in the next section.
6. Network settings, click **Edit**:
   - Create a security group named `priceoptima`.
   - SSH: type SSH, port **22**, source **My IP**.
   - API: type Custom TCP, port **8000**, source **Anywhere-IPv4** (`0.0.0.0/0`). The GitHub-hosted runner curls this port after a deploy. Port 80 is an alternative if you set `HOST_PORT=80` in `.env.prod` and open 80 instead.
7. Advanced details, **IAM instance profile**: select `PriceOptimaEc2`.
8. Storage: 20 GB gp3 is enough for a few images plus the 1 GB swap file. The free-tier default of 8 GB is tight once three images are kept.
9. Click **Launch instance**.
10. Wait until the instance state is **Running**. Copy the public IPv4 address.

Attach the role later if you forgot it:

1. Select the instance.
2. Click **Actions**, **Security**, **Modify IAM role**.
3. Choose `PriceOptimaEc2`. Click **Update IAM role**.

## 4. GitHub Actions SSH key

On your laptop, not on the instance:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/priceoptima -C priceoptima-deploy
```

SSH to the instance with the key pair from the launch wizard and append the new public key:

```bash
ssh -i ~/.ssh/<launch-wizard-key>.pem ubuntu@<EC2_HOST>
# Amazon Linux uses ec2-user instead of ubuntu
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<paste the one line from ~/.ssh/priceoptima.pub>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

Confirm the new key works, then record the host fingerprint:

```bash
ssh -i ~/.ssh/priceoptima ubuntu@<EC2_HOST> 'echo ok'
ssh-keyscan -t ed25519 <EC2_HOST> | ssh-keygen -lf -
```

Copy the `SHA256:...` value into the `EC2_SSH_FINGERPRINT` secret. Paste the private key file into `EC2_SSH_KEY`. The other secrets are listed in `docs/SECRETS.md`.

## 5. Bootstrap

The clone must contain `scripts/ec2_bootstrap.sh` and `.env.prod.example`, so merge this phase to `main` first, or clone your branch by setting `REPO_URL`.

```bash
ssh -i ~/.ssh/priceoptima ubuntu@<EC2_HOST>
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/shreyanshhhhhhhh/MLOps_FinaL.git
bash MLOps_FinaL/scripts/ec2_bootstrap.sh
exit
```

Open a new SSH session afterwards. The `docker` group is applied on the next login. Run the script again any time. It will not overwrite `/opt/priceoptima/.env.prod`.

Edit the env file if the region or the git URL differs. Leave AWS keys out of it.

```bash
chmod 600 /opt/priceoptima/.env.prod
```

`ec2_bootstrap.sh` already sets that mode when it creates the file.

## 6. Reboot test

Run this after the first successful `scripts/deploy.sh`, when `docker ps` shows `priceoptima`.

```bash
ssh -i ~/.ssh/priceoptima ubuntu@<EC2_HOST>
docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' priceoptima
systemctl is-enabled docker
sudo reboot
```

Wait about two minutes. The SSH session will drop. Connect again and check that Docker started the same container without a new deploy:

```bash
ssh -i ~/.ssh/priceoptima ubuntu@<EC2_HOST>
docker ps --filter name=priceoptima
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8000/model-info
```

`unless-stopped` plus `systemctl enable docker` is the whole mechanism. A `docker kill` is a manual stop and stays down until `docker start` or `scripts/deploy.sh`. A reboot is not a manual stop, so the container comes back. From your laptop, `curl -fsS http://<EC2_HOST>:8000/ready` checks the security group as well.

## 7. Stop the instance when you are done

1. EC2 console, select `priceoptima`.
2. **Instance state**, **Stop instance**.
3. Confirm.

A stopped instance does not accrue compute charges. An Elastic IP that stays attached to a stopped instance does. This guide uses the auto-assigned public IP, which changes after a stop/start. Update the `EC2_HOST` secret and `EC2_SSH_FINGERPRINT` if the address changes. Release any Elastic IP you created and do not need.
