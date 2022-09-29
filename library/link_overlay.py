#!/usr/bin/python3
# -*- coding: utf-8

# Copyright: Eike <eike@zettelkiste.de>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from ansible.module_utils.basic import AnsibleModule
from typing import Dict
import os

MODULE_ARGS = {
    "overlay": {
        "description": [
            "Directory or file on the managed node to overlay the target.",
            "Symlinks will point to this directory."
        ],
        "type": "str",
        "required": True
    },
    "target": {
        "description": (
            "Directory on the managed node where the symlinks will be created."
        ),
        "type": "str",
        "required": True
    },
    "relative": {
        "description": "Whether the symlinks will be relative or absolute",
        "type": "bool",
        "required": False,
        "default": True
    },
    "conflict": {
        "description": [
            "Behaviour when a file or symlink pointed outside of overlay "
            + "already exists where a symlink should be created.",
            "error: Fails on conflicts.",
            "ignore: Ignores overlay file and keeps the original.",
            "warning: Like ignore, but prints a warning.",
            "replace: Replaces original file with symlink to overlay."
        ],
        "type": "str",
        "required": False,
        "default": "error",
        "choices": ["error", "warning", "ignore", "replace"]
    },
    # "recursive": {
    #     "description": [
    #         "If overlay is a directory, recursive decides if a single "
    #         + "symlink to the directory will be created (False) or "
    #         + "if symlinks for each file inside overlay and overlay "
    #         + "subdirectories will be created (True).",
    #         "If overlay is a file, recursive has no effect and a single "
    #         + "symlink to the file will be created."
    #     ],
    #     "type": "bool",
    #     "required": False,
    #     "default": True
    # },
    "exclusive": {
        # TODO: you cant always traverse the whole target directory to find
        # broken symlinks.
        # add collapse option and only remove symlinks on the same level as
        # existing symlinks?
        "description": [
            "If set to True, broken symlinks from target pointing into "
            + "overlay will be removed.",
            "If set to False, broken symlinks into overlay will be kept."
        ],
        "type": "bool",
        "required": False,
        "default": True
    },
}


def generate_option_doc(
    option_name: str,
        option_attributes: Dict,
        indent: str = " "*4
):
    doc_string = indent + option_name + ":\n"
    for name, val in option_attributes.items():
        doc_string += indent * 2 + str(name) + ": "

        if isinstance(val, list):
            value_string = '\n'.join(str(line) for line in val)
        elif hasattr(val, "__name__"):
            value_string = val.__name__
        else:
            value_string = str(val)

        lines = [
            line.strip().replace('"', "'")
            for line in value_string.split("\n")
        ]
        if len(lines) > 1:
            doc_string += '['
            doc_string += ", ".join('"' + line + '"' for line in lines)
            doc_string += "]\n"
        else:
            doc_string += lines[0] + '\n'


def generate_options_doc():
    return ''.join(generate_option_doc(name, attrs)
                   for name, attrs in MODULE_ARGS.items())


DOCUMENTATION = (
    r'''
---
module: link_overlay

short_description: Overlay a directory tree onto a target via symlinks

description: This module creates and manages directories and symlinks to overlay one directory tree onto another.

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


def points_to(link, path):
    assert os.path.islink(link)
    return os.path.realpath(link) == os.path.realpath(path)


def points_into(link, path):
    assert os.path.islink(link)
    return (
        os.path.commonpath(
            os.path.realpath(link),
            os.path.realpath(path)
        ) == path
    )


def recursive_scandir(path: str):
    entries = []
    with os.scandir(os.path.abspath(path)) as it:
        for entry in it:
            entries.append(entry)
            if entry.is_dir(follow_symlinks=True):
                entries += recursive_scandir(entry.path)
    return entries


def run_module():
    result = {"changed": False, "original_message": "", "message": ""}

    module = AnsibleModule(
        argument_spec=MODULE_ARGS,
        supports_check_mode=True
    )

    target = os.path.abspath(module.params["target"])
    overlay = os.path.abspath(module.params["overlay"])
    # recursive = module.params["recursive"]

    if not os.path.exists(target):
        module.fail_json(msg="Target does not exist", **result)

    if not os.path.exists(overlay):
        module.fail_json(msg="Overlay does not exist", **result)

    if os.path.isfile(overlay):  # or not recursive:
        overlay_paths = ["."]
    else:
        overlay_paths = [
            os.path.relpath(entry.path, overlay)
            for entry in recursive_scandir(overlay)
        ]

    overlay_files = [path for path in overlay_paths if path.is_file()]
    target_files = [
        os.path.join(target, overlay_file)
        for overlay_file in overlay_files
    ]

    conflicts = []
    existing = []
    for overlay_file, target_file in zip(overlay_files, target_files):
        if not os.path.exists(target_file):
            continue

        if os.path.islink(target_file):
            if points_to(target_file, overlay_file):
                existing.append(overlay_file)
                continue
            if points_into(target_file, overlay):
                continue

        conflicts.append(target_file)

    if len(conflicts) > 0:
        message = "Conflicts found:\n"
        for conflict in conflicts:
            message += conflict + '\n'

        if module.params["conflict"] == "error":
            module.fail_json(msg=message, **result)
        elif module.params["conflict"] == "warning":
            module.warn(message)

    missing = set(overlay)

    # if the user is working with this module in only check mode we do not
    # want to make any changes to the environment, just return the current
    # state with no modifications
    if module.check_mode:
        module.exit_json(**result)

    # manipulate or modify the state as needed (this is going to be the
    # part where your module will do what it needs to do)
    result['original_message'] = module.params['name']
    result['message'] = 'goodbye'

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
