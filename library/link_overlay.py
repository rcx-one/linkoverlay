#!/usr/bin/python3
# -*- coding: utf-8

# Copyright: Eike <eike@zettelkiste.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import AnsibleModule
from typing import Dict, List, Optional
import os
from os import path as osp
from dataclasses import dataclass

MODULE_ARGS = {
    "base_dir": {
        "description": [
            "The directory on the managed node where the overlay will be "
            + "applied.",

            "All symlinks pointing into overlay_dir will be created in this "
            + "directory."
        ],
        "type": "str",
        "required": True
    },
    "overlay_dir": {
        "description": [
            "The directory on the managed node where the overlay files "
            + "reside.",

            "All created symlinks will point into this directory."
        ],
        "type": "str",
        "required": True
    },
    "relative_links": {
        "description": (
            "Whether relative or absolute symlinks will be created."
        ),
        "type": "bool",
        "required": False,
        "default": True
    },
    "conflict": {
        "description": [
            "How files existing in both the base_dir tree and the overlay_dir "
            + "tree will be handled:",

            "error: Will fail on conflict.",

            "ignore: Will ignore overlay files and keep the base files.",

            "warning: Like ignore, but will print a warning.",

            "replace: Will replace original file with symlink to overlay.",

            "Symlinks pointing into overlay_dir are always replaced."
        ],
        "type": "str",
        "required": False,
        "default": "error",
        "choices": ["error", "warning", "ignore", "replace"]
    },
    "collapse": {
        "description": [
            "Whether non-conflicting directory trees will be collapsed into a "
            + "single symlink.",

            "If enabled, will create symlinks to whole subtrees of the "
            + "overlay_dir if they dont conflict with the base_dir.",

            "If disabled, will only create symlinks to leaves of the "
            + "overlay_dir tree and creates missing directories in the "
            + "base_dir."
        ],
        "type": "bool",
        "required": False,
        "default": True,
    },
}


def generate_option_doc(
    option_name: str, option_attributes: Dict, indent: str = " "*4
) -> str:
    doc_string = indent + option_name + ":\n"
    for name, val in option_attributes.items():
        doc_string += indent * 2 + str(name) + ": "

        if isinstance(val, list):
            value_string = "\n".join(str(line) for line in val)
        elif hasattr(val, "__name__"):
            value_string = val.__name__
        else:
            value_string = str(val)

        lines = [
            line.strip().replace('"', "'")
            for line in value_string.split("\n")
        ]
        if len(lines) > 1:
            doc_string += "["
            doc_string += ", ".join('"' + line + '"' for line in lines)
            doc_string += "]\n"
        else:
            doc_string += lines[0] + "\n"
    return doc_string


def generate_options_doc():
    return "".join(generate_option_doc(name, attrs)
                   for name, attrs in MODULE_ARGS.items())


DOCUMENTATION = (
    r'''
---
module: link_overlay

short_description: Overlay a directory tree onto a base via symlinks

description: This module creates and manages symlinks (and directories) to overlay one directory tree onto another.

version_added: "2.3.4"

author: Eike (https://git.rcx.one/eike)

options:
'''
    + generate_options_doc()
    + r'''
# Specify this value according to your collection
# in format of namespace.collection.doc_fragment_name
extends_documentation_fragment:
    - my_namespace.my_collection.my_doc_fragment_name

'''
)

EXAMPLES = r'''
# Pass in a message
- name: Test with a message
  my_namespace.my_collection.my_test:
    name: hello world

# pass in a message and have changed true
- name: Test with a message and changed output
  my_namespace.my_collection.my_test:
    name: hello world
    new: true

# fail the module
- name: Test failure of the module
  my_namespace.my_collection.my_test:
    name: fail me
'''

RETURN = r'''
# These are examples of possible return values, and in general should use other names for return values.
original_message:
    description: The original name param that was passed in.
    type: str
    returned: always
    sample: 'hello world'
message:
    description: The output message that the test module generates.
    type: str
    returned: always
    sample: 'goodbye'
'''


@dataclass
class Tree():
    """A class representing a filesystem directory tree.
    This tree may or may not actually exist on the filesystem.
    Symlinks are treated like files.
    """
    path: str
    children: List["Tree"]
    is_dir: bool
    depth: Optional[int]

    @staticmethod
    def from_path(path: str, depth: Optional[int] = None) -> "Tree":
        """Creates a tree recursively from an existing path.
        Does not recurse into symlinks to directories.
        """
        assert depth is None or depth >= 0
        assert osp.isabs(path)
        assert osp.exists(path)

        is_dir = osp.isdir(path) and not osp.islink(path)

        children = []
        if is_dir and depth != 0:
            child_depth = None if depth is None else depth - 1
            children = [
                Tree.from_path(child, child_depth)
                for child
                in map(lambda p: osp.join(path, p), os.listdir(path))
            ]

        elif not osp.isdir(path) and not osp.isfile(path):
            raise Exception("Path exists, but is neither file nor directory?!")

        return Tree(
            path=path,
            children=children,
            is_dir=is_dir,
            depth=depth
        )

    @property
    def name(self):
        return osp.basename(self.name)

    @property
    def files(self):
        if self.is_dir:
            files = []
            for child in self.children:
                files += child.files
            return files
        else:
            return [self.path]

    def apply(self, func):
        """Applies a function to this tree and all its children recursively.
        """
        func(self)
        for child in self.children:
            child.apply(func)

    def map(self, func):
        """Like apply, but captures the function output in recursive list.
        """
        return [func(self), [child.map(func) for child in self.children]]

    def all(self, func):
        """True, if func returns true for this tree and all of its children
        """
        return func(self) and all(child.all(func) for child in self.children)

    def any(self, func):
        """True, if func returns true for this tree or any of its children
        """
        return func(self) or any(child.any(func) for child in self.children)


def run_module():
    result = {"changed": False, "message": ""}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    base_dir = osp.expanduser(module.params["base_dir"])
    overlay_dir = osp.expanduser(module.params["overlay_dir"])

    if not osp.isdir(base_dir):
        module.fail_json(
            msg="base_dir has to exist and be a directory", **result
        )
    if not osp.isdir(overlay_dir):
        module.fail_json(
            msg="overlay_dir has to exist and be a directory", **result
        )

    for overlay_path in os.listdir(overlay_dir):
        base_path = osp.join(base_dir, osp.relpath(overlay_path, overlay_dir))

    if module.check_mode:
        module.exit_json(**result)

    # use whatever logic you need to determine whether or not this module
    # made any modifications to your target
    if module.params['new']:
        result['changed'] = True

    # during the execution of the module, if there is an exception or a
    # conditional state that effectively causes a failure, run
    # AnsibleModule.fail_json() to pass in the message and the result
    if module.params['name'] == 'fail me':
        module.fail_json(msg='You requested this to fail', **result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
