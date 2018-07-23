"""This script creates an EC2 instance to run the service on."""
import boto3
import time


ec2 = boto3.resource('ec2')
vol = ec2.Volume('vol-0063f68897644be53')


args = \
    {'InstanceType': 'm5.4xlarge',
     'MinCount': 1,
     'MaxCount': 1,
     'ImageId': 'ami-759bc50a', # base Ubuntu
     # 'ImageId': 'ami-29f01a3f', # Rasmachine
     'TagSpecifications': [{
         'ResourceType': 'instance',
         'Tags': [
            {'Key': 'project',
             'Value': 'cwc'}
            ]
        }],
     'KeyName': 'bgyori_ec2',
     'Placement': {
        'AvailabilityZone': 'us-east-1d',
        },
    'SecurityGroupIds': ['sg-a18caad4'] # cwc-integ-security-group
    }
#instance_type = 'r4.2xlarge'


# Step 1 create the instance
instances = ec2.create_instances(**args)
instance = instances[0]


# Step 2 wait for the instance to come online
time.sleep(30)
instance.attach_volume(VolumeId='vol-0063f68897644be53', Device='/dev/sdy')


# Step 3: do this in your terminal
# ssh -i <your RSA private key> ubuntu@<the public IP of the instance>

