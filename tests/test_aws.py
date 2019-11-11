import os
import unittest
import boto3
import json
from moto import mock_autoscaling, mock_ec2
from lib.aws import get_asg_tag, instance_outdated_launchconfiguration, count_all_cluster_instances, is_asg_healthy, is_asg_scaled, modify_aws_autoscaling, save_asg_tags, delete_asg_tags, instance_terminated
from unittest.mock import patch


@mock_autoscaling
@mock_ec2
class TestAWS(unittest.TestCase):

    def setUp(self):
        client = boto3.client('autoscaling')
        # create asg
        client.create_launch_configuration(
            LaunchConfigurationName='mock-lc-01',
            ImageId='string',
            KeyName='string',
            SecurityGroups=['string'],
            UserData='string',
            InstanceId='string',
            InstanceType='string',
            InstanceMonitoring={
                'Enabled': True
            },
        )

        client.create_auto_scaling_group(
            AutoScalingGroupName='mock-asg',
            LaunchConfigurationName='mock-lc-01',
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
        response = client.describe_auto_scaling_groups(AutoScalingGroupNames=['mock-asg'])
        self.instance_id = response['AutoScalingGroups'][0]['Instances'][0]['InstanceId']
        current_dir = os.path.dirname(os.path.abspath(__file__))
        with open(f"{current_dir}/fixtures/aws_response_unhealthy.json", "r") as file:
            self.aws_response_mock_unhealthy = json.load(file)

        with open(f"{current_dir}/fixtures/aws_response_terminated.json", "r") as file:
            self.aws_response_mock_terminated = json.load(file)

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
            self.assertFalse(instance_outdated_launchconfiguration(instances[0], 'mock-lc-01'))

    def test_is_instance_outdated_fail(self):
        response = self.aws_response_mock_unhealthy
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            self.assertTrue(instance_outdated_launchconfiguration(instances[0], 'mock-lc-01'))

    def test_count_all_cluster_instances(self):
        count = count_all_cluster_instances('mock-cluster')
        self.assertEqual(count, 3)

    def test_count_all_cluster_instances_fail(self):
        count = count_all_cluster_instances('foo-bar')
        self.assertEqual(count, 0)

    def test_is_asg_healthy(self):
        result = is_asg_healthy('mock-asg', 2, 1)
        self.assertTrue(result)

    def test_is_asg_healthy_fail(self):
        with patch('lib.aws.client.describe_auto_scaling_groups') as describe_auto_scaling_groups_mock:
            describe_auto_scaling_groups_mock.return_value = self.aws_response_mock_unhealthy
            result = is_asg_healthy('mock-asg', 2, 1)
            self.assertFalse(result)

    def test_is_asg_scaled(self):
        self.assertTrue(is_asg_scaled('mock-asg', 3))

    def test_modify_aws_autoscaling_suspend(self):
        response = modify_aws_autoscaling('mock-asg', 'suspend')
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        self.assertEqual(status_code, 200)

    def test_modify_aws_autoscaling_fail(self):
        with self.assertRaises(Exception):
            modify_aws_autoscaling('mock-asg', 'foo')

    def test_save_asg_tags(self):
        response = save_asg_tags('mock-asg', 'foo', 'bar')
        status_code = response['ResponseMetadata']['HTTPStatusCode']
        self.assertEqual(status_code, 200)

    def test_delete_asg_tags(self):
        with self.assertRaises(NotImplementedError):
            delete_asg_tags('mock-asg', 'foo')

    def test_instance_terminated(self):
        with patch('lib.aws.ec2_client.describe_instances') as describe_instances_mock:
            describe_instances_mock.return_value = self.aws_response_mock_terminated
            self.assertTrue(instance_terminated(self.instance_id, 2, 1))

    def test_instance_terminated_fail(self):
        self.assertFalse(instance_terminated(self.instance_id, 2, 1))
