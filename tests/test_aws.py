
import unittest
import boto3
import json
from moto import mock_autoscaling
from lib.aws import get_asg_tag, get_asgs, instance_outdated, count_all_cluster_instances, is_asg_healthy, is_asg_scaled
from unittest.mock import Mock, patch
from mock import mock


@mock_autoscaling
class TestAWS(unittest.TestCase):

    def setUp(self):

        client = boto3.client('autoscaling')
        # create asg
        client.create_launch_configuration(
            LaunchConfigurationName='mock-lc',
            ImageId='string',
            KeyName='string',
            SecurityGroups=['string'],
            ClassicLinkVPCId='string',
            ClassicLinkVPCSecurityGroups=['string'],
            UserData='string',
            InstanceId='string',
            InstanceType='string',
            InstanceMonitoring={
                'Enabled': True
            },
        )

        client.create_auto_scaling_group(
            AutoScalingGroupName='mock-asg',
            LaunchConfigurationName='mock-lc',
            MinSize=3,
            MaxSize=6,
            DesiredCapacity=3,
            AvailabilityZones=['eu-west-1'],
            Tags=[{
                'ResourceId': 'mock-asg',
                'ResourceType': 'auto-scaling-group',
                'Key': 'kubernetes.io/cluster/mock-cluster',
                'Value': 'owned',
                'PropagateAtLaunch': False
                }
            ]
        )

    def test_get_asg_tag(self):
        tags = [
            {
                'ResourceId': 'string',
                'ResourceType': 'string',
                'Key': 'eks-rolling-update:desired_capacity',
                'Value': '6',
                'PropagateAtLaunch': True
            },

        ]
        response = get_asg_tag(tags, "eks-rolling-update:desired_capacity")
        self.assertEqual(response, tags[0])

    def test_get_asg_tag_fail(self):
        tags = [
            {
                'ResourceId': 'string',
                'ResourceType': 'string',
                'Key': 'eks-rolling-update:desired_capacity',
                'Value': '6',
                'PropagateAtLaunch': True
            },

        ]
        response = get_asg_tag(tags, "foo")
        self.assertEqual(response, {})

    def test_is_instance_outdated(self):
        client = boto3.client('autoscaling')
        response = client.describe_auto_scaling_groups(AutoScalingGroupNames=['mock-asg'])
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
        self.assertFalse(instance_outdated(instances[0], 'mock-lc'))

    def test_count_all_cluster_instances(self):
        count = count_all_cluster_instances('mock-cluster')
        self.assertEqual(count, 3)

    def test_count_all_cluster_instances_fail(self):
        count = count_all_cluster_instances('foo-bar')
        self.assertEqual(count, 0)

    def test_is_asg_healthy(self):
        result = is_asg_healthy('mock-asg', 2, 1)
        self.assertTrue(result)

    def test_is_asg_scaled(self):
        self.assertTrue(is_asg_scaled('mock-asg', 3))
