"""ROS 导航动作节点"""

import py_trees
from py_trees.behaviour import Behaviour
from py_trees.common import Status


class NavigationAction(Behaviour):
    """
    通过 ROS 发布导航目标。

    当 intent == "navigation" 时执行，否则返回 FAILURE。
    预留 ROS 接口，实际使用时通过 rclpy 或 rosbridge 通信。
    """

    def __init__(self, name: str):
        super().__init__(name)

        self.blackboard = self.attach_blackboard_client(
            name="NavigationAction", namespace="dialog"
        )
        self.blackboard.register_key(
            key="intent", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="user_command", access=py_trees.common.Access.READ
        )
        self.blackboard.register_key(
            key="response_text", access=py_trees.common.Access.WRITE
        )

    def update(self):
        if self.blackboard.intent != "navigation":
            return Status.FAILURE

        command = self.blackboard.user_command
        self.logger.info(f"执行: 导航 ({command})")

        # TODO: 通过 ROS topic / service / action 发布导航目标
        #
        # ROS 2 示例 (rclpy):
        #   import rclpy
        #   from geometry_msgs.msg import PoseStamped
        #   from nav2_simple_commander.robot_navigator import BasicNavigator
        #
        #   navigator = BasicNavigator()
        #   goal_pose = PoseStamped()
        #   goal_pose.header.frame_id = 'map'
        #   goal_pose.pose.position.x = 1.0
        #   goal_pose.pose.position.y = 2.0
        #   navigator.goToPose(goal_pose)
        #
        # rosbridge 示例:
        #   import roslibpy
        #   client = roslibpy.Ros(host='localhost', port=9090)
        #   publisher = roslibpy.Topic(client, '/goal_pose', 'geometry_msgs/PoseStamped')
        #   publisher.publish(roslibpy.Message({...}))

        self.blackboard.response_text = "好的，正在为您导航。"
        return Status.SUCCESS
