# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.plugins.callback import CallbackBase
from ansible.executor.task_result import TaskResult
from ansible.playbook.task import Task
from ansible.playbook.play import Play
from ansible.playbook import Playbook

from ansible.template import Templar
from ansible.plugins.strategy import SharedPluginLoaderObj
from ansible.inventory.host import Host

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

    def _all_vars(self, host: Host, task: Task):
        return self.play.get_variable_manager().get_vars(
            loader=self.playbook.get_loader(),
            play=self.play,
            host=host,
            task=task
        )

    def _write_result(self, journal_path: str, task: Task, result):
        if result.get("skipped", False):
            return
        if (task.get_name() == "ansible.builtin.file"
                and result.get("state") == "absent"):
            return

        path = result.get("dest", result.get("path"))

        with open(journal_path, "a") as file:
            if path is None:
                task_name = task.get_name().replace("\n", "\\n")
                file.write(f"!{task_name}: missing path argument\n")
            else:
                file.write(f"{path}\n")

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

    def v2_playbook_on_start(self, playbook: Playbook):
        self.playbook = playbook

    def v2_playbook_on_play_start(self, play: Play):
        self.play = play

    def v2_runner_item_on_ok(self, result: TaskResult):
        super().v2_runner_item_on_ok(result)
        task: Task = result._task
        host: Host = result._host
        task_result: dict = result._result

        templar = Templar(
            loader=self.playbook.get_loader(),
            shared_loader_obj=SharedPluginLoaderObj(),
            variables=self._all_vars(host=host, task=task)
        )

        path = templar.template(task.get_vars().get("journal_path"))

        if path is not None:
            self._write_result(path, task, task_result)
