
import unittest
import boto3
import json
from moto import mock_autoscaling
from eks_rolling_update import get_asg_tag, get_asgs, instance_outdated, count_all_cluster_instances, is_asg_healthy, get_k8s_nodes, k8s_nodes_count, k8s_nodes_ready, get_node_by_instance_id, is_asg_scaled
from unittest.mock import Mock, patch
from mock import mock


class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__



@mock_autoscaling
class Test(unittest.TestCase):

    def setUp(self):

        client = boto3.client('autoscaling')
        # create asg
        client.create_launch_configuration(
            LaunchConfigurationName='mock-lc',
            ImageId='string',
            KeyName='string',
            SecurityGroups=['string',],
            ClassicLinkVPCId='string',
            ClassicLinkVPCSecurityGroups=['string',],
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

        with open("tests/fixtures/k8s_response.json", "r") as file:
            self.k8s_response_mock = json.load(file)

        with open("tests/fixtures/k8s_response_unhealthy.json", "r") as file:
            self.k8s_response_mock_unhealthy = json.load(file)

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

    def test_k8s_node_count(self):
        with patch('eks_rolling_update.get_k8s_nodes') as mock_nodes:
            mock_nodes.return_value = self.k8s_response_mock['items']
            self.assertTrue(k8s_nodes_count(3, 2, 1))

    def test_k8s_node_count_fail(self):
        with patch('eks_rolling_update.get_k8s_nodes') as mock_nodes:
            mock_nodes.return_value = self.k8s_response_mock['items']
            self.assertFalse(k8s_nodes_count(4, 2, 1))

    def test_get_node_by_instance_id_fail(self):
        with patch('eks_rolling_update.get_k8s_nodes') as mock_nodes:
            mock_nodes.return_value = self.k8s_response_mock['items']
            with self.assertRaises(Exception):
                get_node_by_instance_id(mock_nodes, 'i-5c407d0022735edff')

    def test_is_asg_scaled(self):
        self.assertTrue(is_asg_scaled('mock-asg', 3))



