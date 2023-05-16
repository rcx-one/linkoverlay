# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.callback import CallbackBase
from ansible.executor.task_result import TaskResult
from ansible.playbook.task import Task
# from ansible.inventory.host import Host

DOCUMENTATION = """
    name: journal
    type: notification
    short_description: logs files created by tasks to a list in a file
    version_added: "0.1.0"
    description:
        - "Whenever a task has a variable 'journal_path: <path-to-file>', "
        - "paths kept present by that task are appended to the given file."
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 0.1
    CALLBACK_TYPE = "notification"
    CALLBACK_NAME = "rcx_one.linkoverlay.journal"
    CALLBACK_NEEDS_ENABLED = False

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display=display)

    def v2_runner_on_ok(self, result: TaskResult):
        super().v2_runner_on_ok(result)
        task: Task = result._task
        # host: Host = result._host
        result: dict = result._result

        path = task.get_vars().get("journal_path")
        if path is not None:
            with open(path, "a") as file:
                if "results" in result:
                    results = result["results"]
                else:
                    results = [result]

                for r in results:
                    invocation = r["invocation"]
                    if (
                        "module_args" not in invocation
                        or "path" not in invocation["module_args"]
                    ):
                        name = task.get_name().replace("\n", "\\n")
                        file.write(f"!{name}: path argument missing\n")
                        continue

                    args = invocation["module_args"]
                    if args.get("state", "present") != "absent":
                        file.write(args["path"] + "\n")

    def v2_runner_on_failed(self, result, ignore_errors=False):
        super().v2_runner_on_ok(result)
        task: Task = result._task
        # host: Host = result._host
        result: dict = result._result

        path = task.get_vars().get("journal_path")
        if path is not None:
            with open(path, "a") as file:
                name = task.get_name().replace("\n", "\\n")
                file.write(f"!{name}: failed\n")
