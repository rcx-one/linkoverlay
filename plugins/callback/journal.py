# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.callback import CallbackBase
from ansible.executor.task_result import TaskResult
from typing import List
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
        task_result: dict = result._result

        if "results" in task_result:  # loops get handled by v2_runner_item_*
            return

        path = task.get_vars().get("journal_path")
        if path is not None:
            self._write_result(path, task, task_result)

    def v2_runner_item_on_ok(self, result: TaskResult):
        super().v2_runner_item_on_ok(result)
        task: Task = result._task
        # host: Host = result._host
        task_result: dict = result._result

        path = task.get_vars().get("journal_path")
        if path is not None:
            self._write_result(path, task, task_result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        super().v2_runner_on_failed(result, ignore_errors=ignore_errors)
        task: Task = result._task
        # host: Host = result._host
        task_result: dict = result._result

        if not ignore_errors:
            return
        if "results" in task_result:  # loops get handled by v2_runner_item_*
            return

        path = task.get_vars().get("journal_path")
        if path is not None:
            # TODO: add info about failed task
            self._write_error(path, task, task_result, "failed")

    def v2_runner_on_item_failed(self, result, ignore_errors=False):
        super().v2_runner_on_item_failed(result, ignore_errors=ignore_errors)
        task: Task = result._task
        # host: Host = result._host
        task_result: dict = result._result

        if not ignore_errors:
            return

        path = task.get_vars().get("journal_path")
        if path is not None:
            # TODO: add info about failed item
            self._write_error(path, task, task_result, "failed with item")

    def _write_result(self, journal_path: str, task: Task, result):
        if result.get("skipped", False):
            return
        if (task.get_name() == "ansible.builtin.file"
                and result.get("state") == "absent"):
            return

        path = result.get("dest", result.get("path"))
        if path is None:
            self._write_error(
                journal_path,
                task,
                result,
                "missing path argument"
            )

        with open(journal_path, "a") as file:
            file.write(f"{path}\n")

    def _write_error(self, journal_path: str, task: Task, result, msg):
        with open(journal_path, "a") as file:
            task_name = task.get_name().replace("\n", "\\n")
            msg = msg.replace("\n", "\\n")
            file.write(f"!{task_name}: {msg}\n")
