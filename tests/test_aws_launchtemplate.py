import os
import unittest
import json
from moto import mock_autoscaling, mock_ec2
from eksrollup.lib.aws import instance_outdated_launchtemplate
from unittest.mock import patch


@mock_autoscaling
@mock_ec2
class TestAWS(unittest.TestCase):

    def setUp(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        with open(f"{current_dir}/fixtures/aws_response_launchtemplate.json", "r") as file:
            self.aws_response_mock = json.load(file)
        with open(f"{current_dir}/fixtures/aws_response_launchtemplate_default.json", "r") as file:
            self.aws_response_mock_default = json.load(file)
        with open(f"{current_dir}/fixtures/aws_response_launchtemplate_latest.json", "r") as file:
            self.aws_response_mock_latest = json.load(file)
        with open(f"{current_dir}/fixtures/get_launch_template.json", "r") as file:
            self.mock_get_launch_template = json.load(file)

    def test_is_instance_outdated(self):
        response = self.aws_response_mock
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            self.assertFalse(instance_outdated_launchtemplate(instances[0], 'mock-lt-01', '2'))

    def test_is_instance_outdated_fail_name(self):
        response = self.aws_response_mock
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            self.assertTrue(instance_outdated_launchtemplate(instances[1], 'mock-lt-01', '2'))

    def test_is_instance_outdated_fail_version_number(self):
        response = self.aws_response_mock
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            self.assertTrue(instance_outdated_launchtemplate(instances[2], 'mock-lt-01', '2'))

    def test_is_instance_outdated_fail_version_default(self):
        response = self.aws_response_mock_default
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            with patch('eksrollup.lib.aws.get_launch_template') as get_launch_template_mock:
                get_launch_template_mock.return_value = self.mock_get_launch_template
                self.assertTrue(instance_outdated_launchtemplate(instances[0], 'mock-lt-01', '$Default'))

    def test_is_instance_outdated_pass_version_default(self):
        response = self.aws_response_mock_default
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            with patch('eksrollup.lib.aws.get_launch_template') as get_launch_template_mock:
                get_launch_template_mock.return_value = self.mock_get_launch_template
                self.assertFalse(instance_outdated_launchtemplate(instances[2], 'mock-lt-01', '$Default'))

    def test_is_instance_outdated_pass_version_latest(self):
        response = self.aws_response_mock_latest
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            with patch('eksrollup.lib.aws.get_launch_template') as get_launch_template_mock:
                get_launch_template_mock.return_value = self.mock_get_launch_template
                self.assertFalse(instance_outdated_launchtemplate(instances[0], 'mock-lt-01', '$Latest'))

    def test_is_instance_outdated_fail_version_latest(self):
        response = self.aws_response_mock_latest
        asgs = response['AutoScalingGroups']
        for asg in asgs:
            instances = asg['Instances']
            with patch('eksrollup.lib.aws.get_launch_template') as get_launch_template_mock:
                get_launch_template_mock.return_value = self.mock_get_launch_template
                self.assertTrue(instance_outdated_launchtemplate(instances[2], 'mock-lt-01', '$Latest'))
