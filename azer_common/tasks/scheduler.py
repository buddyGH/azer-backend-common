from apscheduler.schedulers.background import BackgroundScheduler

# 初始化调度器
scheduler = BackgroundScheduler()


# TODO:定期清除过期权限和角色
# 定期任务：暂
async def fake_scheduler():
    print("Scheduler run...")


# 添加清理任务，每天凌晨运行
scheduler.add_job(fake_scheduler, "cron", hour=0)


# 启动调度器函数
def start_verification_code_cleanup_scheduler():
    print("Scheduler start...")
    scheduler.start()


def stop_verification_code_cleanup_scheduler():
    print("Scheduler stop...")
    scheduler.shutdown(wait=False)
