"""
aws_deploy.py — Live AWS Infrastructure Provisioner for M5 v2
Region: ap-south-1 (Mumbai)
"""

import os
import sys
import time
import json
import boto3

AWS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

session = boto3.Session(
    aws_access_key_id=AWS_KEY_ID,
    aws_secret_access_key=AWS_SECRET,
    region_name=AWS_REGION
)
ec2 = session.client("ec2")
ssm = session.client("ssm")

def step1_security_group():
    print("\n" + "="*70)
    print("STEP 1: Creating & Configuring AWS Security Group (m5-production-sg)")
    print("="*70)
    
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "is-default", "Values": ["true"]}])
    vpc_id = vpcs["Vpcs"][0]["VpcId"]
    print(f"[+] Found Default VPC: {vpc_id}")

    sg_name = "m5-production-sg"
    try:
        sg_res = ec2.create_security_group(
            GroupName=sg_name,
            Description="M5 v2 Context Engine Security Group (HTTP/HTTPS/SSH)",
            VpcId=vpc_id
        )
        sg_id = sg_res["GroupId"]
        print(f"[+] Created New Security Group: {sg_name} -> ID: {sg_id}")
    except Exception as e:
        if "InvalidGroup.Duplicate" in str(e):
            sgs = ec2.describe_security_groups(GroupNames=[sg_name])
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            print(f"[+] Security Group already exists: {sg_name} -> ID: {sg_id}")
        else:
            raise e

    # Inbound firewall rules
    rules = [
        {"IpProtocol": "tcp", "FromPort": 80, "ToPort": 80, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTP"}]},
        {"IpProtocol": "tcp", "FromPort": 443, "ToPort": 443, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "HTTPS"}]},
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "IpRanges": [{"CidrIp": "0.0.0.0/0", "Description": "SSH"}]},
    ]

    for rule in rules:
        port = rule["FromPort"]
        desc = rule["IpRanges"][0]["Description"]
        try:
            ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[rule])
            print(f"    [OK] Allowed Port {port} ({desc}) from 0.0.0.0/0")
        except Exception as e:
            if "InvalidPermission.Duplicate" in str(e):
                print(f"    [OK] Port {port} ({desc}) already authorized")
            else:
                print(f"    [WARN] Port {port} rule error: {str(e)}")

    print(f"[SUCCESS] Security Group Configured: {sg_id}")
    return sg_id

def step2_key_pair():
    print("\n" + "="*70)
    print("STEP 2: Creating SSH Key Pair (m5-ec2-key.pem)")
    print("="*70)
    
    key_name = "m5-ec2-key"
    pem_path = os.path.join(os.path.dirname(__file__), f"{key_name}.pem")

    try:
        key_res = ec2.create_key_pair(KeyName=key_name, KeyType="rsa", KeyFormat="pem")
        with open(pem_path, "w", encoding="utf-8") as f:
            f.write(key_res["KeyMaterial"])
        print(f"[+] Created New SSH Key Pair: {key_name}")
        print(f"[+] Saved Private Key to: {pem_path}")
        print(f"    Fingerprint: {key_res.get('KeyFingerprint')}")
    except Exception as e:
        if "InvalidKeyPair.Duplicate" in str(e):
            print(f"[+] Key Pair '{key_name}' already exists in AWS.")
            if os.path.exists(pem_path):
                print(f"[+] Local private key verified at: {pem_path}")
            else:
                print(f"[!] Note: Key exists on AWS. Reusing existing key pair.")
        else:
            raise e

    print(f"[SUCCESS] SSH Key Pair '{key_name}' is ready.")
    return key_name

def step3_get_ubuntu_ami():
    print("\n" + "="*70)
    print("STEP 3: Resolving Latest Official Ubuntu 24.04 LTS AMI")
    print("="*70)
    
    # Query AWS official Canonical Ubuntu 24.04 parameter
    try:
        param = ssm.get_parameter(
            Name="/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
        )
        ami_id = param["Parameter"]["Value"]
        print(f"[+] Resolved Official Ubuntu 24.04 LTS AMI: {ami_id} (ap-south-1)")
        return ami_id
    except Exception:
        # Fallback to direct EC2 search
        images = ec2.describe_images(
            Owners=["099720109477"], # Canonical
            Filters=[
                {"Name": "name", "Values": ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]},
                {"Name": "state", "Values": ["available"]}
            ]
        )["Images"]
        images.sort(key=lambda x: x["CreationDate"], reverse=True)
        ami_id = images[0]["ImageId"]
        print(f"[+] Resolved Ubuntu 24.04 AMI: {ami_id} ({images[0]['Name']})")
        return ami_id

def step4_launch_ec2(sg_id: str, key_name: str, ami_id: str):
    print("\n" + "="*70)
    print("STEP 4: Launching EC2 Instance (t3.large + 50GB Encrypted EBS)")
    print("="*70)

    # Cloud-init UserData bootstrap script
    user_data_script = """#!/bin/bash
set -e
exec > /var/log/m5-bootstrap.log 2>&1

echo "[+] Starting M5 v2 Cloud-Init Bootstrap..."
apt-get update -y
apt-get install -y docker.io docker-compose-v2 git curl nginx

systemctl enable docker
systemctl start docker

# Configure Nginx Reverse Proxy
cat << 'EOF' > /etc/nginx/sites-available/m5.conf
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}
EOF

ln -sf /etc/nginx/sites-available/m5.conf /etc/nginx/sites-enabled/default
systemctl restart nginx

# Clone and deploy M5
mkdir -p /opt/m5
cd /opt/m5
git clone https://github.com/lazyserp/M5-v2.git . || git pull

# Create production .env
cat << 'EOF' > .env
M5_ADMIN_KEY=m5_admin_2d961a6681027ca971b76d2101a4e175ffdd21a745d203dc
QDRANT_URL=http://qdrant:6333
EOF

docker compose up --build -d
echo "[SUCCESS] M5 v2 Production Engine is online!"
"""

    block_device_mappings = [
        {
            "DeviceName": "/dev/sda1",
            "Ebs": {
                "VolumeSize": 50,
                "VolumeType": "gp3",
                "DeleteOnTermination": True,
                "Encrypted": True
            }
        }
    ]

    instance_res = ec2.run_instances(
        ImageId=ami_id,
        InstanceType="t3.large",
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        MinCount=1,
        MaxCount=1,
        BlockDeviceMappings=block_device_mappings,
        UserData=user_data_script,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "m5-context-server"},
                    {"Key": "Project", "Value": "M5-v2"}
                ]
            }
        ]
    )

    instance_id = instance_res["Instances"][0]["InstanceId"]
    print(f"[+] EC2 Instance Created: {instance_id}")
    print(f"    • Instance Type: t3.large (2 vCPU, 8GB RAM)")
    print(f"    • Storage:       50GB gp3 (AWS KMS Encrypted)")
    print(f"    • Initial State: {instance_res['Instances'][0]['State']['Name']}")
    
    print("\n[+] Waiting for instance to enter 'running' state...")
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    
    desc = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]
    public_ip = desc.get("PublicIpAddress", "Pending")
    print(f"[SUCCESS] Instance is RUNNING! Initial Public IP: {public_ip}")
    return instance_id, public_ip

def step5_allocate_elastic_ip(instance_id: str):
    print("\n" + "="*70)
    print("STEP 5: Allocating & Attaching Static Elastic IP")
    print("="*70)
    
    try:
        # Check if already has elastic IP
        eip_res = ec2.allocate_address(
            Domain="vpc",
            TagSpecifications=[{
                "ResourceType": "elastic-ip",
                "Tags": [{"Key": "Name", "Value": "m5-production-ip"}]
            }]
        )
        allocation_id = eip_res["AllocationId"]
        elastic_ip = eip_res["PublicIp"]
        print(f"[+] Allocated Elastic Static IPv4: {elastic_ip} ({allocation_id})")

        # Associate with instance
        ec2.associate_address(InstanceId=instance_id, AllocationId=allocation_id)
        print(f"[SUCCESS] Attached Elastic IP {elastic_ip} -> Instance {instance_id}")
        return elastic_ip
    except Exception as e:
        print(f"[!] Elastic IP allocation notice: {str(e)}")
        return None

if __name__ == "__main__":
    print("="*70)
    print("M5 v2 — AWS PRODUCTION DEPLOYMENT STARTING (ap-south-1)")
    print("="*70)
    
    sg_id = step1_security_group()
    key_name = step2_key_pair()
    ami_id = step3_get_ubuntu_ami()
    instance_id, pub_ip = step4_launch_ec2(sg_id, key_name, ami_id)
    elastic_ip = step5_allocate_elastic_ip(instance_id)

    final_ip = elastic_ip or pub_ip
    print("\n" + "="*70)
    print("🎉 DEPLOYMENT LAUNCH COMPLETE!")
    print("="*70)
    print(f"  • Instance ID:     {instance_id}")
    print(f"  • Region:          ap-south-1 (Mumbai)")
    print(f"  • Public IP:       {final_ip}")
    print(f"  • Health Probe:    http://{final_ip}/health")
    print(f"  • Remote MCP:      http://{final_ip}/mcp")
    print(f"  • Swagger Docs:    http://{final_ip}/docs")
    print("="*70 + "\n")
