#!/usr/bin/python3
# -*- coding: utf-8

# Copyright: Eike <eike@zettelkiste.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import AnsibleModule
from typing import Dict, List, Optional, Callable
import os
from os import path as osp
from dataclasses import dataclass, field
from copy import deepcopy

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
    # "state": {
    #     "description": [
    #         "All created symlinks will point into this directory."
    #     ],
    #     "type": "str",
    #     "required": False,
    #     "default": "linked",
    #     "choices": ["linked", "unlinked"]
    # },
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

            "If disabled, will only create missing directories and symlinks "
            + "to leaves of the overlay_dir tree in the base_dir."
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
    """
    path: str
    children: List["Tree"]
    is_dir: bool
    depth: Optional[int]
    props: Dict = field(default_factory=dict, init=False)

    def __str__(self):
        return self.path

    def __fspath__(self):
        return self.path

    @staticmethod
    def from_path(path: str, depth: Optional[int] = None) -> "Tree":
        """Creates a tree recursively from an existing path.
        Symlinks are treated like files and are not recursed into.
        """
        assert depth is None or depth >= 0
        assert osp.isabs(path)
        assert osp.exists(path)

        is_dir = osp.isdir(path) and not osp.islink(path)

        if is_dir and depth != 0:
            child_depth = None if depth is None else depth - 1
            children = [
                Tree.from_path(child, child_depth)
                for child
                in map(lambda p: osp.join(path, p), os.listdir(path))
            ]
        elif osp.isdir(path) or osp.isfile(path):
            children = []
        else:
            raise Exception("Path exists, but is neither file nor directory?!")

        return Tree(
            path=path,
            children=children,
            is_dir=is_dir,
            depth=depth
        )

    @property
    def name(self) -> str:
        return osp.basename(self.name)

    @property
    def files(self) -> List[str]:
        if self.is_dir:
            files = []
            for child in self.children:
                files += child.files
            return files
        else:
            return [self.path]

    def apply(self, func: Callable, stopping: bool = False):
        """Applies a function to this tree and all its children recursively.
        If stopping is True, stops recursing once func returns False.
        """
        ret = func(self)
        if not stopping or ret:
            for child in self.children:
                child.apply(func, stopping)

    def all(self, func: Callable) -> bool:
        """True, if func returns true for this tree and all of its children.
        """
        return func(self) and all(child.all(func) for child in self.children)

    def any(self, func: Callable) -> bool:
        """True, if func returns true for this tree or any of its children.
        """
        return func(self) or any(child.any(func) for child in self.children)

    def apply_children(self, func: Callable, stopping: bool = False):
        """Like apply, but only applies to children of self.
        """
        for child in self.children:
            child.apply(func, stopping)

    def all_children(self, func: Callable) -> bool:
        """Like all, but only inspects children of self.
        """
        return all(child.all(func) for child in self.children)

    def any_children(self, func: Callable) -> bool:
        """Like any, but only inspects children self.
        """
        return any(child.any(func) for child in self.children)

    def translate(self, old_base: str, new_base: str):
        assert osp.abspath(self.path) == osp.abspath(old_base)
        assert old_base == self.path or osp.commonpath([old_base, self.path])

        translated = deepcopy(self)

        def func(t: Tree):
            t.path = osp.join(new_base, osp.relpath(t.path, old_base))

        translated.apply(func)
        return translated


def is_inside(inner, outer):
    inner = osp.abspath(inner)
    outer = osp.abspath(outer)
    return osp.commonpath([outer, inner]) == outer


def points_into(link, path):
    return os.readlink(link)


def run_module():
    result = {"changed": False, "message": ""}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    base_dir = osp.expanduser(module.params["base_dir"])
    overlay_dir = osp.expanduser(module.params["overlay_dir"])

    if not osp.isdir(base_dir) or osp.islink(base_dir):
        module.fail_json(
            msg="base_dir has to exist and be a directory", **result
        )
    if not osp.isdir(overlay_dir) or osp.islink(overlay_dir):
        module.fail_json(
            msg="overlay_dir has to exist and be a directory", **result
        )
    if osp.samefile(base_dir, overlay_dir) or is_inside(base_dir, overlay_dir):
        module.fail_json(
            msg="base_dir must not be (inside) overlay_dir", **result
        )

    overlay_tree = Tree.from_path(overlay_dir)
    base_tree = overlay_tree.translate(overlay_dir, base_dir)

    def not_conflicting(tree: Tree):
        # Trees do not conflict if they don't exist in base_dir,
        # are links into overlay_dir or are directories
        return (
            not osp.exists(tree)
            or osp.islink(tree) and points_into(tree, overlay_tree)
            or not osp.islink(tree) and osp.isdir(tree)
        )

    base_tree.apply_children(lambda t: print(not_conflicting(t), t))
    x = []
    base_tree.apply(lambda t: x.append(t.path))
    for i in x:
        print(i)

    if module.check_mode:
        module.exit_json(**result)

    # in the event of a successful module execution, you will want to
    # simple AnsibleModule.exit_json(), passing the key/value results
    module.exit_json(**result)


def main():
    run_module()


if __name__ == '__main__':
    main()
