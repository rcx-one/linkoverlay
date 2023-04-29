#!/usr/bin/python
# -*- coding: utf-8

# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

DOCUMENTATION = """
module: clean
short_description: Removed file from given path excluding a list of files
description: This module recursively removes all files and directories inside the given path as long as that does not mean removing any of the paths that were excluded.
version_added: 1.0.0
author: Eike (@E1k3)
options:
  path:
    description: The path to be cleaned.
    type: path
    required: true
  exclude:
    description: The list of paths not to be removed.
    type: list
    requred: false
    default: []
"""

EXAMPLES = """
- name: Remove old synced files
  rcx_one.linkoverlay.clean:
    path: "/home/user/dotfiles"
    exclude:
      - "/home/user/dotfiles/keep_me"
"""

RETURN = """
removed:
    description: Removed paths
    returned: changed
    type: list
    sample: ["/home/user/old_file"]
"""

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type
from ansible.module_utils.basic import AnsibleModule
from typing import List, Dict
import os
from os import path as osp
from shutil import rmtree

try:
    from ansible.module_utils import linkoverlay as lo
except ImportError:
    from module_utils import linkoverlay as lo

MODULE_ARGS = {
    "path": {
        "type": "path",
        "required": True
    },
    "exclude": {
        "type": "list",
        "default": [],
        "required": False
    }
}


def clean(path: os.PathLike, exclude: List[os.PathLike], result: Dict):
    if path not in exclude:
        matching = [ex for ex in exclude if not lo.is_inside(ex, path)]
        if not matching:
            if osp.islink(path) or osp.isfile(path):
                os.unlink(path)
            else:
                rmtree(path)
            result["changed"] = True
            result.setdefault("removed", []).append(path)

        elif not osp.islink(path) and osp.isdir(path):
            for entry in os.listdir(path):
                clean(entry, matching, result)


def main():
    result = {"changed": False}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    path = module.params["path"]
    exclude = module.params["exclude"]

    for entry in os.listdir(path):
        clean(entry, exclude, result)
