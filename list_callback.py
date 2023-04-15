from ansible.plugins.callback import CallbackBase
from yaml import dump
from ansible.executor.task_result import TaskResult
from ansible.playbook.task import Task
from ansible.inventory.host import Host


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 0.1
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "community.link_overlay.callback"
    CALLBACK_NEEDS_ENABLED = False

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display=display)
        self.file = open("/home/eike/meh.txt", "w")

    def write(self, **data):
        def meh(x):
            if isinstance(x, (list, tuple, set)):
                return [meh(v) for v in x]
            if isinstance(x, dict):
                return {meh(k): meh(v) for k, v in x.items()}
            return str(x)
        dump(
            meh(data),
            self.file, explicit_start=True
        )

    def v2_runner_on_ok(self, result: TaskResult):
        super().v2_runner_on_ok(result)
        task: Task = result._task
        host: Host = result._host
        result: dict = result._result
        if "foo" in task.tags:
            self.write(v2_runner_on_ok=(host.get_name(), {"task": task.dump_attrs(), "result": result}))
