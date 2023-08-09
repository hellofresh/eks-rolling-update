from eksrollup.lib import aws as eksrollup_aws
from eksrollup.lib import k8s as eksrollup_k8s
from kubernetes import client, config
import os
from time import sleep
from typing import Any, Dict, List

app_config_default = {
    "PYTHONIOENCODING": "utf-8",
    "K8S_AUTOSCALER_ENABLED": "1",
    "K8S_AUTOSCALER_NAMESPACE": "kube-system",
    "K8S_AUTOSCALER_DEPLOYMENT": "cluster-autoscaler",
    "K8S_AUTOSCALER_REPLICAS": "1",
    "EXTRA_DRAIN_ARGS": "--force=true --timeout=600s",
    "INSTANCE_WAIT_FOR_STOPPING": "1",
    "POST_DRAIN_SLEEP_SECONDS": "0",
    "CLUSTER_HEALTH_RETRY": "3",
    "CLUSTER_HEALTH_WAIT": "120",
    "ASG_USE_TERMINATION_POLICY": "True",
    "ENFORCED_DRAINING": "True",
}


class BatchPod:
    def __init__(self, name):
        self.name = name


class JobsClusterNode:
    def __init__(self, name, node_group):
        self.name = name
        self.node_group = node_group

    @property
    def running_batch_worker_pods(self) -> List[BatchPod]:
        v1 = client.CoreV1Api()
        ret = v1.list_pod_for_all_namespaces(
            watch=False,
            label_selector="app=batch-deploy",
            field_selector=f"status.phase=Running,spec.nodeName={self.name}"
        )
        return [BatchPod(name=pod.metadata.name) for pod in ret.items]


class AutoScalingGroup:
    def __init__(self, asg_info: Dict[str, Any]):
        self.name = asg_info['AutoScalingGroupName']
        self.arg = asg_info['AutoScalingGroupARN']
        self.node_group = next(
            tag['Value'] for tag in asg_info['Tags']
            if tag['Key'] == 'k8s.io/cluster-autoscaler/node-template/label/cosmos.affirm.com/worker_name'
        )
        self.min_size = asg_info['MinSize']
        self.max_size = asg_info['MaxSize']
        self.desired_capacity = asg_info['DesiredCapacity']


class JobsCluster:
    def __init__(self, cluster_name: str):
        self.cluster_name = cluster_name
        self.nodes = [
            JobsClusterNode(
                name=node.metadata.name,
                node_group=node.metadata.labels["cosmos.affirm.com/worker_name"]
            ) for node in eksrollup_k8s.get_k8s_nodes()
        ]
        self.asgs = [
            AutoScalingGroup(asg_info) for asg_info in eksrollup_aws.get_asgs(self.cluster_name)
        ]
        self.cordoned_nodes = []

    @property
    def worker_nodes(self) -> List[JobsClusterNode]:
        return [node for node in self.nodes if "airflow" not in node.node_group]

    @property
    def airflow_nodes(self) -> List[JobsClusterNode]:
        return [node for node in self.nodes if "airflow" in node.node_group]

    @property
    def airflow_asgs(self):
        return [asg for asg in self.asgs if "airflow" in asg.node_group]

    @staticmethod
    def get_all_running_pods() -> List[BatchPod]:
        v1 = client.CoreV1Api()
        ret = v1.list_pod_for_all_namespaces(
            watch=False,
            label_selector="app=batch-deploy",
            field_selector="status.phase=Running"
        )
        return [BatchPod(name=pod.metadata.name) for pod in ret.items]

    def cordon_worker_nodes(self):
        for worker_node in self.worker_nodes:
            eksrollup_k8s.cordon_node(worker_node.name)
            self.cordoned_nodes.append(worker_node)

    def check_and_drain_nodes(self):
        for cordoned_node in self.cordoned_nodes:
            if len(cordoned_node.running_batch_worker_pods) == 0:
                print(f'Draining node: {cordoned_node.name}')
                eksrollup_k8s.drain_node(cordoned_node.name)
                self.cordoned_nodes.remove(cordoned_node)

    def cycle_worker_nodes(self):
        """
        Cycle worker nodes.
        (1) Cordon the nodes
        (2) Poll the tainted nodes until all jobs complete
        (3) Drain each node once jobs have completed
        """
        self.cordon_worker_nodes()
        while len(self.cordoned_nodes) > 0:
            self.check_and_drain_nodes()

            if len(self.cordoned_nodes) > 0:
                sleep_duration = 60
                print(f'Worker nodes still running jobs, sleeping for {sleep_duration}')
                sleep(sleep_duration)

def print_node_info(nodes: List[JobsClusterNode]):
    for node in nodes:
        print(
            f'''
                --------------------------------------------------------
                Name:               {node.name}
                Node Group:         {node.node_group}
                --------------------------------------------------------
                '''
        )

        for pod in node.running_batch_worker_pods:
            print(
                f'''
                Pod Name:   {pod.name}
                '''
            )


def main():
    for (key, value) in app_config_default.items():
        os.environ[key] = value

    cluster = JobsCluster(cluster_name="stage-live-jobs")
    print('\n====================================Worker Nodes====================================\n')
    print_node_info(cluster.worker_nodes)
    print('\n====================================Airflow Nodes====================================\n')
    print_node_info(cluster.airflow_nodes)
    print('\n====================================ASGs====================================\n')
    # for asg in cluster.asgs:
    #     print(f"{asg.name}\n{asg.node_group}")

    # uncomment to cycle worker nodes
    print("\n====================================Begin Node Cycling====================================\n")
    cluster.cycle_worker_nodes()


if __name__ == '__main__':
    main()
