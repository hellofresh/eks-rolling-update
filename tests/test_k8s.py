import os
import unittest
import json
import re
from eksrollup.lib.k8s import k8s_nodes_count, k8s_nodes_ready, get_node_by_instance_id, ensure_config_loaded, pods_in_ready_state, match_k8s_pods, get_k8s_pods
from unittest.mock import patch
from box import Box
from kubernetes.client import ApiClient
from kubernetes.config import kube_config

class TestK8S(unittest.TestCase):

    def setUp(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))

        with open(f"{current_dir}/fixtures/k8s_response.json", "r") as file:
            self.k8s_response_mock = json.load(file)

        with open(f"{current_dir}/fixtures/k8s_response_unhealthy.json", "r") as file:
            self.k8s_response_mock_unhealthy = json.load(file)

        with open(f"{current_dir}/fixtures/k8s_response_pods_ready.json", "r") as file:
            self.k8s_response_mock_pod_ready = json.load(file)

        with open(f"{current_dir}/fixtures/k8s_response_pods_not_ready.json", "r") as file:
            self.k8s_response_mock_pod_not_ready = json.load(file)

        kube_config.KUBE_CONFIG_DEFAULT_LOCATION = f"{current_dir}/fixtures/example-kube-config.yaml"
        print(f"Using test kube config at {kube_config.KUBE_CONFIG_DEFAULT_LOCATION}")

    def test_ensure_config_loaded_proxy_default(self):
        ensure_config_loaded()
        self.assertEqual(None, ApiClient().configuration.proxy)

    def test_ensure_config_loaded_proxy_prefers_https(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://localhost:12345', 'HTTP_PROXY': 'http://localhost:6789'}):
            ensure_config_loaded()
            self.assertEqual('http://localhost:12345', ApiClient().configuration.proxy)

    def test_ensure_config_loaded_proxy_fallback_to_http(self):
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://localhost:12345'}):
            ensure_config_loaded()
            self.assertEqual('http://localhost:12345', ApiClient().configuration.proxy)

    @patch.dict("eksrollup.lib.k8s.app_config", {'K8S_PROXY_BYPASS': True})
    def test_ensure_config_loaded_proxy_not_set_when_no_k8s_set(self):
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://localhost:6789'}):
            ensure_config_loaded()
            self.assertNotEqual('http://localhost:6789', ApiClient().configuration.proxy)

    def test_k8s_node_count(self):
        with patch('eksrollup.lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            self.assertTrue(k8s_nodes_count(3, 2, 1))

    def test_k8s_node_count_fail(self):
        with patch('eksrollup.lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            self.assertFalse(k8s_nodes_count(4, 2, 1))

    def test_get_node_by_instance_id_fail(self):
        with patch('eksrollup.lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            get_k8s_nodes_mock.return_value = self.k8s_response_mock['items']
            with self.assertRaises(Exception):
                get_node_by_instance_id(get_k8s_nodes_mock, 'i-0a000b00000000cdee')

    def test_k8s_nodes_ready(self):
        with patch('eksrollup.lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            box = Box(self.k8s_response_mock, ordered_box=True)
            get_k8s_nodes_mock.return_value = box['items']
            self.assertTrue(k8s_nodes_ready(2, 1), True)

    def test_k8s_nodes_ready_fail(self):
        with patch('eksrollup.lib.k8s.get_k8s_nodes') as get_k8s_nodes_mock:
            box = Box(self.k8s_response_mock_unhealthy, ordered_box=True)
            get_k8s_nodes_mock.return_value = box['items']
            self.assertFalse(k8s_nodes_ready(2, 1), False)

    def test_k8s_pods_ready(self):
        with patch('eksrollup.lib.k8s.get_k8s_pods') as get_k8s_pods_mock:
            get_k8s_pods_mock.return_value = self.k8s_response_mock_pod_ready['items']
            matched_pods = match_k8s_pods(get_k8s_pods_mock.return_value, re.compile(r"^test_"))
            self.assertTrue(pods_in_ready_state(matched_pods), True)

    def test_k8s_pods_ready_fail(self):
        with patch('eksrollup.lib.k8s.get_k8s_pods') as get_k8s_pods_mock:
            get_k8s_pods_mock.return_value = self.k8s_response_mock_pod_not_ready['items']
            matched_pods = match_k8s_pods(get_k8s_pods_mock.return_value, re.compile(r"^test_"))
            self.assertFalse(pods_in_ready_state(matched_pods), False)
