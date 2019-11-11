import os
import unittest
import json
from lib.k8s import k8s_nodes_count, k8s_nodes_ready, get_node_by_instance_id
from unittest.mock import patch
from box import Box


class TestK8S(unittest.TestCase):

    def setUp(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))

        with open(f"{current_dir}/fixtures/k8s_response.json", "r") as file:
            self.k8s_response_mock = json.load(file)

        with open(f"{current_dir}/fixtures/k8s_response_unhealthy.json", "r") as file:
            self.k8s_response_mock_unhealthy = json.load(file)

    def test_k8s_node_count(self):
        with patch('lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            self.assertTrue(k8s_nodes_count(3, 2, 1))

    def test_k8s_node_count_fail(self):
        with patch('lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            self.assertFalse(k8s_nodes_count(4, 2, 1))

    def test_get_node_by_instance_id_fail(self):
        with patch('lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            with self.assertRaises(Exception):
                get_node_by_instance_id(get_k8s_nodes_mock, 'i-0a000b00000000cdee')

    def test_k8s_nodes_ready(self):
        with patch('lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            box = Box(self.k8s_response_mock, ordered_box=True)
            get_k8s_nodes_mock.return_value = box['items']
            self.assertTrue(k8s_nodes_ready(2, 1), True)

    def test_k8s_nodes_ready_fail(self):
        with patch('lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            box = Box(self.k8s_response_mock_unhealthy, ordered_box=True)
            get_k8s_nodes_mock.return_value = box['items']
            self.assertFalse(k8s_nodes_ready(2, 1), False)

