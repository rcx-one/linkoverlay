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
        dump(
            {k: str(v) for k, v in data.items()},
            self.file, explicit_start=True
        )

    # def set_play_context(self, play_context):
    #     self.write(set_play_context=play_context)

    # def on_any(self, *args, **kwargs):
    #     self.write(on_any=(args, kwargs))

    # def runner_on_failed(self, host, res, ignore_errors=False):
    #     self.write(runner_on_failed=(host, res, ignore_errors))

    # def runner_on_ok(self, host, res):
    #     self.write(runner_on_ok=(host, res, self._plugin_options))

    # def runner_on_skipped(self, host, item=None):
    #     self.write(runner_on_skipped=(host, item))

    # def runner_on_unreachable(self, host, res):
    #     self.write(runner_on_unreachable=(host, res))

    # def runner_on_no_hosts(self):
    #     self.write(runner_on_no_hosts="no hosts")

    # def runner_on_async_poll(self, host, res, jid, clock):
    #     self.write(runner_on_async_poll=(host, res, jid, clock))

    # def runner_on_async_ok(self, host, res, jid):
    #     self.write(runner_on_async_ok=(host, res, jid))

    # def runner_on_async_failed(self, host, res, jid):
    #     self.write(runner_on_async_failed=(host, res, jid))

    # def playbook_on_start(self):
    #     self.write(playbook_on_start="playbook start")

    # def playbook_on_notify(self, host, handler):
    #     self.write(playbook_on_notify=(host, handler))

    # def playbook_on_no_hosts_matched(self):
    #     self.write(playbook_on_no_hosts_matched="no hosts matched")

    # def playbook_on_no_hosts_remaining(self):
    #     self.write(playbook_on_no_hosts_remaining="no hosts remaining")

    # def playbook_on_task_start(self, name, is_conditional):
    #     self.write(playbook_on_task_start=(name, is_conditional))

    # def playbook_on_vars_prompt(
    #         self,
    #         varname,
    #         private=True,
    #         prompt=None,
    #         encrypt=None,
    #         confirm=False,
    #         salt_size=None,
    #         salt=None,
    #         default=None,
    #         unsafe=None
    # ):
    #     self.write(
    #         playbook_on_vars_prompt=(
    #             varname,
    #             private,
    #             prompt,
    #             encrypt,
    #             confirm,
    #             salt_size,
    #             salt,
    #             default,
    #             unsafe
    #         )
    #     )

    # def playbook_on_setup(self):
    #     self.write(playbook_on_setup="setup")

    # def playbook_on_import_for_host(self, host, imported_file):
    #     self.write(playbook_on_import_for_host=(host, imported_file))

    # def playbook_on_not_import_for_host(self, host, missing_file):
    #     self.write(playbook_on_not_import_for_host=(host, missing_file))

    # def playbook_on_play_start(self, name):
    #     self.write(playbook_on_play_start=name)

    # def playbook_on_stats(self, stats):
    #     self.write(playbook_on_stats=stats)

    # def on_file_diff(self, host, diff):
    #     self.write(on_file_diff=(host, diff))

    # def v2_playbook_on_include(self, included_file):
    #     self.write(v2_playbook_on_include=included_file)

    # def v2_runner_item_on_ok(self, result):
    #     self.write(v2_runner_item_on_ok=result.__dict__)

    # def v2_runner_item_on_failed(self, result):
    #     self.write(v2_runner_item_on_failed=result.__dict__)

    # def v2_runner_item_on_skipped(self, result):
    #     self.write(v2_runner_item_on_skipped=result.__dict__)

    # def v2_runner_retry(self, result):
    #     self.write(v2_runner_retry=result.__dict__)

    # def v2_runner_on_start(self, host, task):
    #     self.write(v2_runner_on_start=(host, task, task.__dict__))

    def v2_runner_on_ok(self, result: TaskResult):
        super().v2_runner_on_ok(result)
        task: Task = result._task
        host: Host = result._host
        if "foo" in task.tags:
            self.write(v2_runner_on_ok=(host.get_name(), result.task_name))
