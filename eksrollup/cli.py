import sys
import argparse
import time
import shutil
from .config import app_config
from .lib.logger import logger
from .lib.aws import is_asg_scaled, is_asg_healthy, instance_terminated, get_asg_tag, modify_aws_autoscaling, \
    count_all_cluster_instances, save_asg_tags, get_asgs, scale_asg, plan_asgs, terminate_instance_in_asg, delete_asg_tags
from .lib.k8s import k8s_nodes_count, k8s_nodes_ready, get_k8s_nodes, modify_k8s_autoscaler, get_node_by_instance_id, \
    drain_node, delete_node, cordon_node
from .lib.exceptions import RollingUpdateException


def validate_cluster_health(asg_name, new_desired_asg_capacity, desired_k8s_node_count, ):
    cluster_healthy = False
    # check if asg has enough nodes first before checking instance health
    if is_asg_scaled(asg_name, new_desired_asg_capacity):
        # if asg is healthy start draining and terminating instances
        if is_asg_healthy(asg_name):
            # check if k8s nodes are all online
            if k8s_nodes_count(desired_k8s_node_count):
                # check k8s nodes are healthy
                if k8s_nodes_ready():
                    logger.info('Cluster validation passed. Proceeding with node draining and termination...')
                    cluster_healthy = True
                else:
                    logger.info('Validation failed for cluster. Expected node count reached but nodes are not healthy.')
            else:
                nodes = get_k8s_nodes()
                logger.info('Current k8s node count is {}'.format(len(nodes)))
                logger.info('Validation failed for cluster. Current node count {} Expected node count {}.'.format(
                    len(nodes),
                    desired_k8s_node_count))
        else:
            logger.info(
                'Validation failed for asg {}.'
                'Instances not healthy'.format(asg_name))
    else:
        logger.info('Validation failed for asg {}. Not enough instances online.'.format(asg_name))
    return cluster_healthy


def scale_up_asg(cluster_name, asg, count):
    asg_old_max_size = asg['MaxSize']
    asg_old_desired_capacity = asg['DesiredCapacity']
    desired_capacity = asg_old_desired_capacity + count
    asg_tags = asg['Tags']
    asg_name = asg['AutoScalingGroupName']

    # remove any stale suspensions from asg that may be present
    modify_aws_autoscaling(asg_name, "resume")

    use_asg_termination_policy = app_config['ASG_USE_TERMINATION_POLICY']
    asg_tag_desired_capacity = get_asg_tag(asg_tags, app_config["ASG_DESIRED_STATE_TAG"])
    asg_tag_orig_capacity = get_asg_tag(asg_tags, app_config["ASG_ORIG_CAPACITY_TAG"])
    asg_tag_orig_max_capacity = get_asg_tag(asg_tags, app_config["ASG_ORIG_MAX_CAPACITY_TAG"])

    if desired_capacity == asg_old_desired_capacity:
        logger.info(f'Desired and current capacity for {asg_name} are equal. Skipping ASG.')

        if asg_tag_desired_capacity.get('Value'):
            logger.info('Found capacity tags on ASG from previous run. Leaving alone.')
            return int(asg_tag_desired_capacity.get('Value')), int(asg_tag_orig_capacity.get(
                'Value')), int(asg_tag_orig_max_capacity.get('Value'))
        else:
            save_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"], asg_old_desired_capacity)
            save_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"], asg_old_desired_capacity)
            save_asg_tags(asg_name, app_config["ASG_ORIG_MAX_CAPACITY_TAG"], asg_old_max_size)
            return asg_old_desired_capacity, asg_old_desired_capacity, asg_old_max_size

    # True: use ASG's 'DesiredCapacity' to count the instances
    # False: use Instances list to count the instances
    predictive = True if use_asg_termination_policy else False

    # only scale up if no previous desired capacity tag set
    if asg_tag_desired_capacity.get('Value'):
        logger.info('Found previous desired capacity value tag set on asg from a previous run.')
        logger.info(f'Maintaining previous capacity of {asg_old_desired_capacity} to not overscale.')

        asg_instance_count = count_all_cluster_instances(cluster_name, predictive=predictive)

        # check cluster health before doing anything
        if not validate_cluster_health(
            asg_name,
            int(asg_tag_desired_capacity.get('Value')),
            asg_instance_count
        ):
            logger.info('Exiting since ASG healthcheck failed')
            raise Exception('ASG healthcheck failed')

        return int(asg_tag_desired_capacity.get('Value')), int(asg_tag_orig_capacity.get(
            'Value')), int(asg_tag_orig_max_capacity.get('Value'))
    else:
        logger.info('No previous capacity value tags set on ASG; setting tags.')
        save_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"], asg_old_desired_capacity)
        save_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"], desired_capacity)
        save_asg_tags(asg_name, app_config["ASG_ORIG_MAX_CAPACITY_TAG"], asg_old_max_size)

        # only change the max size if the new capacity is bigger than current max
        if desired_capacity > asg_old_max_size:
            scale_asg(asg_name, asg_old_desired_capacity, desired_capacity, desired_capacity)
        else:
            scale_asg(asg_name, asg_old_desired_capacity, desired_capacity, asg_old_max_size)

        cluster_health_wait = app_config['CLUSTER_HEALTH_WAIT']
        logger.info(f'Waiting for {cluster_health_wait} seconds for ASG to scale before validating cluster health...')
        time.sleep(cluster_health_wait)
        asg_instance_count = count_all_cluster_instances(cluster_name, predictive=predictive)

        # check cluster health before doing anything
        if not validate_cluster_health(
            asg_name,
            desired_capacity,
            asg_instance_count
        ):
            logger.info('Exiting since ASG healthcheck failed')
            raise Exception('ASG healthcheck failed')

        return desired_capacity, asg_old_desired_capacity, asg_old_max_size


def update_asgs(asgs, cluster_name):
    run_mode = app_config['RUN_MODE']
    use_asg_termination_policy = app_config['ASG_USE_TERMINATION_POLICY']
    asg_outdated_instance_dict = plan_asgs(asgs)

    asg_state_dict = {}

    if run_mode == 2:
        # Scale up all the ASGs with outdated nodes (by the number of outdated nodes)
        for asg_name, asg_tuple in asg_outdated_instance_dict.items():
            outdated_instances, asg = asg_tuple
            outdated_instance_count = len(outdated_instances)
            logger.info(
                f'Setting the scale of ASG {asg_name} based on {outdated_instance_count} outdated instances.')
            asg_state_dict[asg_name] = scale_up_asg(cluster_name, asg, outdated_instance_count)

    k8s_nodes = get_k8s_nodes()
    if (run_mode == 2) or (run_mode == 3):
        for asg_name, asg_tuple in asg_outdated_instance_dict.items():
            outdated_instances, asg = asg_tuple
            for outdated in outdated_instances:
                node_name = ""
                try:
                    # get the k8s node name instead of instance id
                    node_name = get_node_by_instance_id(k8s_nodes, outdated['InstanceId'])
                    cordon_node(node_name)
                except Exception as cordon_exception:
                    logger.error(f"Encountered an error when cordoning node {node_name}")
                    logger.error(cordon_exception)
                    exit(1)

    # Drain, Delete and Terminate the outdated nodes and return the ASGs back to their original state
    for asg_name, asg_tuple in asg_outdated_instance_dict.items():
        outdated_instances, asg = asg_tuple
        outdated_instance_count = len(outdated_instances)

        if (run_mode == 1) or (run_mode == 3):
            logger.info(
                f'Setting the scale of ASG {asg_name} based on {outdated_instance_count} outdated instances.')
            asg_state_dict[asg_name] = scale_up_asg(cluster_name, asg, outdated_instance_count)

        if run_mode == 1:
            for outdated in outdated_instances:
                node_name = ""
                try:
                    # get the k8s node name instead of instance id
                    node_name = get_node_by_instance_id(k8s_nodes, outdated['InstanceId'])
                    cordon_node(node_name)
                except Exception as cordon_exception:
                    logger.error(f"Encountered an error when cordoning node {node_name}")
                    logger.error(cordon_exception)
                    exit(1)

        if len(outdated_instances) != 0:
            # if ASG termination is ignored then suspend 'Launch' and 'ReplaceUnhealthy'
            # for this ASG to avoid instances being spawned during terminate/detach phase
            if not use_asg_termination_policy:
                modify_aws_autoscaling(asg_name, "suspend")

        # start draining and terminating
        desired_asg_capacity = asg_state_dict[asg_name][0]
        for outdated in outdated_instances:
            # catch any failures so we can resume aws autoscaling
            try:
                # get the k8s node name instead of instance id
                node_name = get_node_by_instance_id(k8s_nodes, outdated['InstanceId'])
                desired_asg_capacity -= 1
                drain_node(node_name)
                delete_node(node_name)
                save_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"], desired_asg_capacity)
                # terminate/detach outdated instances only if ASG termination policy is ignored
                if not use_asg_termination_policy:
                    terminate_instance_in_asg(outdated['InstanceId'])
                    if not instance_terminated(outdated['InstanceId']):
                        raise Exception('Instance is failing to terminate. Cancelling out.')

                    between_nodes_wait = app_config['BETWEEN_NODES_WAIT']
                    if between_nodes_wait != 0:
                        logger.info(f'Waiting for {between_nodes_wait} seconds before continuing...')
                        time.sleep(between_nodes_wait)
            except Exception as drain_exception:
                logger.info(drain_exception)
                raise RollingUpdateException("Rolling update on ASG failed", asg_name)

        # scaling cluster back down
        logger.info("Scaling asg back down to original state")
        asg_desired_capacity, asg_orig_desired_capacity, asg_orig_max_capacity = asg_state_dict[asg_name]
        scale_asg(asg_name, asg_desired_capacity, asg_orig_desired_capacity, asg_orig_max_capacity)
        # resume aws autoscaling only if ASG termination policy is ignored
        if not use_asg_termination_policy:
            modify_aws_autoscaling(asg_name, "resume")
        # remove aws tag
        delete_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"])
        delete_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"])
        delete_asg_tags(asg_name, app_config["ASG_ORIG_MAX_CAPACITY_TAG"])
        logger.info(f'*** Rolling update of asg {asg_name} is complete! ***')
    logger.info('All asgs processed')


def main(args=None):
    parser = argparse.ArgumentParser(description='Rolling update on cluster')
    parser.add_argument('--cluster_name', '-c', required=True,
                        help='the cluster name to perform rolling update on')
    parser.add_argument('--plan', '-p', action='store_const', const=True,
                        help='perform a dry run to see which instances are out of date')
    args = parser.parse_args(args)
    # check kubectl is installed
    kctl = shutil.which('kubectl')
    if not kctl:
        logger.info('kubectl is required to be installed before proceeding')
        quit(1)
    filtered_asgs = get_asgs(args.cluster_name)
    # perform a dry run
    if args.plan:
        plan_asgs(filtered_asgs)
    else:
        # perform real update
        if app_config['K8S_AUTOSCALER_ENABLED']:
            # pause k8s autoscaler
            modify_k8s_autoscaler("pause")
        try:
            update_asgs(filtered_asgs, args.cluster_name)
            if app_config['K8S_AUTOSCALER_ENABLED']:
                # resume autoscaler after asg updated
                modify_k8s_autoscaler("resume")
            logger.info('*** Rolling update of all asg is complete! ***')
        except Exception as e:
            logger.error(e)
            logger.error('*** Rolling update of ASG has failed. Exiting ***')
            logger.error('AWS Auto Scaling Group processes will need resuming manually')
            if app_config['K8S_AUTOSCALER_ENABLED']:
                logger.error('Kubernetes Cluster Autoscaler will need resuming manually')
            sys.exit(1)
