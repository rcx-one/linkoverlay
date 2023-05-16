#!/usr/bin/python
# -*- coding: utf-8

# Copyright: Eike <ansible@rcx.one>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type


DOCUMENTATION = """
module: clean
short_description: clears a path while keeping files contained in a journal
description: >
  Removes all paths in a directory except those contained in an exclude list.
  Meant to be used with the journal callback or journal role to make sure a
  directory does not contain anything that was not created by ansible.
  Because of this, lines beginning with '!' are interpreted as errors messages.
version_added: 0.1.0
author: Eike (@E1k3)
options:
  path:
    description: The path to be cleaned.
    type: path
    required: true
  exclude:
    description: The list of paths not to be removed.
    type: list
    elements: str
    required: false
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

from ansible.module_utils.basic import AnsibleModule  # noqa: E402
from typing import Set  # noqa: E402
import os  # noqa: E402
from os import path as osp  # noqa: E402
from shutil import rmtree  # noqa: E402
try:
    from ansible_collections.rcx_one.linkoverlay.plugins.module_utils.\
        linkoverlay import Tree
except ImportError:
    from ..module_utils.linkoverlay import Tree

MODULE_ARGS = {
    "path": {
        "type": "path",
        "required": True
    },
    "exclude": {
        "type": "list",
        "elements": "str",
        "default": [],
        "required": False
    }
}


def mark_excluded(tree: Tree, exclude: Set[str]):
    """Marks trees that are excluded or contain excluded trees.
    """
    def impl(tree: Tree) -> bool:
        if tree.path in exclude:
            tree.apply(lambda t: t.set_prop("excluded", True))
            return False  # Stop recursing
        else:
            tree.set_prop("excluded", False)
            return True  # Recurse into children

    tree.apply_children(impl, stopping=True)


def mark_removable(tree: Tree):
    """Marks trees that are not and do not contain excluded trees.
    """
    def impl(tree: Tree):
        tree.set_prop("removable", not tree.any(lambda t: t.props["excluded"]))

    tree.apply_children(impl, stopping=False)


def mark_remove(tree: Tree):
    """Marks roots of subtrees that can be recursively removed.
    """
    def impl(tree: Tree) -> bool:
        if tree.props["removable"]:
            tree.set_prop("remove", True)
            tree.apply_children(lambda t: t.set_prop("remove", False))
            return False  # Stop recursing
        else:
            tree.set_prop("remove", False)
            return True  # Recurse into children

    tree.apply_children(impl, stopping=True)


def main():
    result = {"changed": False}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    path = module.params["path"]
    exclude = set(module.params["exclude"])

    # Build directory tree
    tree = Tree.from_path(path)

    # Mark tree properties
    mark_excluded(tree, exclude)
    mark_removable(tree)

    # Mark planned removals
    mark_remove(tree)

    remove = tree.filter_children(lambda t: t.props["remove"])
    result["removed"] = [tree.path for tree in remove]

    if module.check_mode:
        module.exit_json(**result)

    # Remove marked trees
    for tree in remove:
        if osp.islink(tree) or osp.isfile(tree):
            os.unlink(tree)
        else:
            rmtree(tree)

    module.exit_json(**result)


if __name__ == "__main__":
    main()
