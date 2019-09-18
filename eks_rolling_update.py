import sys
import argparse
import time
import shutil
from config import app_config
from lib.logger import logger
from lib.aws import is_asg_scaled, is_asg_healthy, instance_outdated, instance_terminated, get_asg_tag, modify_aws_autoscaling, count_all_cluster_instances, save_asg_tags, get_asgs, terminate_instance, scale_asg, plan_asgs, delete_asg_tags, detach_instance, instance_detached
from lib.k8s import k8s_nodes_count, k8s_nodes_ready, get_k8s_nodes, modify_k8s_autoscaler, get_node_by_instance_id, drain_node, delete_node
from lib.exceptions import RollingUpdateException


def validate_cluster_health(asg_name, new_desired_asg_capacity, desired_k8s_node_count):
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
        logger.info(
            'Validation failed for asg {}.'
            'Not enough instances online'.format(asg_name))
    return cluster_healthy


def update_asgs(asgs, cluster_name):
    for asg in asgs:
        logger.info('\n')
        logger.info('****  Starting rolling update for autoscaling group {}  ****'.format(asg['AutoScalingGroupName']))
        asg_name = asg['AutoScalingGroupName']
        asg_lc_name = asg['LaunchConfigurationName']
        asg_old_max_size = asg['MaxSize']
        instances = asg['Instances']
        asg_old_desired_capacity = asg['DesiredCapacity']
        asg_tags = asg['Tags']
        # return a list of outdated instances
        outdated_instances = []
        for instance in instances:
            if instance_outdated(instance, asg_lc_name):
                outdated_instances.append(instance)
        logger.info('Found {} outdated instances'.format(
            len(outdated_instances))
        )
        # skip to next asg if there are no outdated instances
        if len(outdated_instances) == 0:
            continue
        # remove any stale suspentions from asg that may be present
        modify_aws_autoscaling(asg_name, "resume")
        # check for previous run tag on asg
        asg_tag_desired_capacity = get_asg_tag(asg_tags, app_config["ASG_DESIRED_STATE_TAG"])
        if asg_tag_desired_capacity.get('Value'):
            logger.info('Found previous desired capacity value tag set on asg from a previous run. Value: {}'.format(asg_tag_desired_capacity.get('Value')))
            logger.info('Maintaining previous capacity to not overscale')
            asg_new_desired_capacity = int(asg_tag_desired_capacity.get('Value'))
            asg_tag_original_capacity = get_asg_tag(asg_tags, app_config["ASG_ORIG_CAPACITY_TAG"])
            logger.info('Maintaining original old capacity from a previous run so we can scale back down to original size of: {}'.format(asg_tag_original_capacity.get('Value')))
            asg_old_desired_capacity = int(asg_tag_original_capacity.get('Value'))
        else:
            logger.info('No previous capacity value tag set on asg')
            # save original capacity to asg tags
            logger.info('Setting original capacity on asg')
            save_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"], asg_old_desired_capacity)
            asg_new_desired_capacity = asg_old_desired_capacity + len(outdated_instances)
            # save new capacity to asg tags
            save_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"], asg_new_desired_capacity)
        # only change the max size if the new capacity is bigger than current max
        if asg_new_desired_capacity > asg_old_max_size:
            asg_new_max_size = asg_new_desired_capacity
        else:
            # dont change the size
            asg_new_max_size = asg_old_max_size
        # get number of k8s nodes before we scale used later
        # to determine how many new nodes have been created
        k8s_nodes = get_k8s_nodes()
        # now scale up
        scale_asg(asg_name, asg_old_desired_capacity, asg_new_desired_capacity, asg_new_max_size)
        logger.info('Waiting for {} seconds for asg {} to scale before validating cluster health...'.format(app_config['CLUSTER_HEALTH_WAIT'], asg_name))
        time.sleep(app_config['CLUSTER_HEALTH_WAIT'])
        # check how many instances are running
        asg_instance_count = count_all_cluster_instances(cluster_name)
        # check cluster health before doing anything
        if validate_cluster_health(
            asg_name,
            asg_new_desired_capacity,
            asg_instance_count
        ):
            # pause aws autoscaling so new instances dont try
            # to spawn while instances are being terminated
            modify_aws_autoscaling(asg_name, "suspend")
            # start draining and terminating
            for outdated in outdated_instances:
                # catch any failures so we can resume aws autoscaling
                try:
                    # get the k8s node name instead of instance id
                    node_name = get_node_by_instance_id(k8s_nodes, outdated['InstanceId'])
                    drain_node(node_name)
                    delete_node(node_name)
                    terminate_instance(outdated['InstanceId'])
                    if not instance_terminated(outdated['InstanceId']):
                        raise Exception('Instance is failing to terminate. Cancelling out.')
                    detach_instance(outdated['InstanceId'], asg_name)
                    if not instance_detached(outdated['InstanceId']):
                        raise Exception('Instance is failing to detach from ASG. Cancelling out.')
                except Exception as e:
                    logger.info(e)
                    raise RollingUpdateException("Rolling update on asg failed", asg_name)

            # resume aws autoscaling
            modify_aws_autoscaling(asg_name, "resume")
            # remove aws tag
            delete_asg_tags(asg_name, app_config["ASG_DESIRED_STATE_TAG"])
            delete_asg_tags(asg_name, app_config["ASG_ORIG_CAPACITY_TAG"])
            logger.info('*** Rolling update of asg {} is complete! ***'.format(asg_name))
        else:
            logger.info('Exiting since asg healthcheck failed')
            raise Exception('Asg healthcheck failed')
    logger.info('All asgs processed')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Rolling update on cluster')
    parser.add_argument('--cluster_name', '-c', required=True,
                        help='the cluster name to perform rolling update on')
    parser.add_argument('--plan', '-p', nargs='?', const=True,
                        help='perform a dry run to see which instances are out of date')
    args = parser.parse_args()
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
            # resume autoscaler after asg updated
            modify_k8s_autoscaler("resume")
            logger.info('*** Rolling update of all asg is complete! ***')
        except RollingUpdateException as e:
            logger.info("Rolling update encountered an exception. Resuming aws autoscaling.")
            modify_aws_autoscaling(e.asg_name, "resume")
            if app_config['K8S_AUTOSCALER_ENABLED']:
                # resume autoscaler no matter what happens
                modify_k8s_autoscaler("resume")
            # Send exit code 1 to the caller so CI shows a failure
            sys.exit(1)
        except Exception as e:
            logger.info(e)
            logger.info('*** Rolling update of asg has failed. Exiting ***')
            if app_config['K8S_AUTOSCALER_ENABLED']:
                # resume autoscaler no matter what happens
                modify_k8s_autoscaler("resume")
            sys.exit(1)
