class DatabaseRouter:
    # noinspection PyMethodMayBeStatic
    def db_for_read(self, model, **hints):
        # 动态选择读库逻辑
        if hints.get("in_transaction"):
            return "master"
        return "replica"

    # noinspection PyMethodMayBeStatic
    def db_for_write(self, model, **hints):
        return "master"

    # noinspection PyMethodMayBeStatic
    def allow_relation(self, obj1, obj2, **hints):
        # 禁止跨数据库关联
        db1 = getattr(obj1, "_saved_in_db", "master")
        db2 = getattr(obj2, "_saved_in_db", "master")
        return db1 == db2

    # noinspection PyMethodMayBeStatic
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # 只允许主库迁移
        return db == "master"
