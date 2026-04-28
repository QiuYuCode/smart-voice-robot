import time

from pyAgxArm import AgxArmFactory, create_agx_arm_config


def main():
    right_arm_cfg = create_agx_arm_config(robot="nero", comm="can", channel="can_right")
    right_robot = AgxArmFactory.create_arm(right_arm_cfg)

    # 连接机械臂
    print("连接机械臂...")
    right_robot.connect()
    
    # 重置机械臂
    right_robot.reset()
    time.sleep(3)
    
    print("使能机械臂中...")  
    while not right_robot.enable():
        print("等待机械臂使能成功...")
        time.sleep(0.1)
    print("机械臂使能成功...")
    
    while not right_robot.set_normal_mode():
        print("等待机械臂设置为正常模式成功...")
        time.sleep(0.01)
    print("机械臂设置为正常模式成功...")
    
    
    # 设置机械臂为主模式
    # time.sleep(3)
    # right_robot.set_leader_mode()
    
    # 设置机械臂为从臂模式
    # right_robot.set_follower_mode()
    
    # 紧急停止机械臂
    # right_robot.electronic_emergency_stop()
    

    # 获取从臂/普通模式下的关节角度
    # while True:
    #     joint_angles = right_robot.get_joint_angles()
    #     if joint_angles is not None:
    #         print("right_joint_angles_msg:", joint_angles.msg)
    #         print(
    #             "right_joint_angles_hz:", joint_angles.hz,
    #             "right_joint_angles_timestamp:", joint_angles.timestamp,
    #         )
    #     time.sleep(0.005)
        
    # 获取主臂模式下的关节角度
    # while True:
    #     joint_angles = right_robot.get_leader_joint_angles()
    #     if joint_angles is not None:
    #         print("right_leader_joint_angles_msg:", joint_angles.msg)
    #         print(
    #             "right_leader_joint_angles_hz:", joint_angles.hz,
    #             "right_leader_joint_angles_timestamp:", joint_angles.timestamp,
    #         )
    #     time.sleep(0.005)

    # 控制机械臂运动
    # right_robot.set_speed_percent(20)
    # # 以左臂为参照，右臂的 1 ， 3 ， 5, 6 关节角度与左臂相反
    # right_robot.move_j([-0.1, 0.5, -0.2, 0.2, -0.5, -0.5, 0.5])
    # # right_robot.move_j([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    
    # time.sleep(0.5)
    # start_t = time.monotonic()
    # while True:
    #     status = right_robot.get_arm_status()
    #     if status is not None and status.msg.motion_status == 0:
    #         print("已到达目标位置")
    #         break
    #     if time.monotonic() - start_t > 5.0:
    #         print("等待运动结束超时（5s）")
    #         break
    #     time.sleep(0.1)

if __name__ == "__main__":
    main()
