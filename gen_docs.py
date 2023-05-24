#!/usr/bin/env python
from plugins.modules.linkoverlay import MODULE_ARGS
from yaml import safe_load, safe_dump


documented_keys = [
    "description",
    "required",
    "default",
    "choices",
    "type",
    "elements",
    "aliases",
    "version_added",
    "suboptions"
]

license_comment = (
    "# GNU General Public License v3.0+ "
    + "(see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)\n"
)


if __name__ == "__main__":
    docs = {
        name: {
            key: val
            for key, val in doc.items()
            if key in documented_keys
        }
        for name, doc in MODULE_ARGS.items()
    }

    with open("plugins/modules/linkoverlay.partial.yml") as doc_partial:
        doc_yml = safe_load(doc_partial)
    doc_yml["DOCUMENTATION"]["options"] = docs
    with open("plugins/modules/linkoverlay.yml", "w") as doc_file:
        doc_string = safe_dump(
            doc_yml,
            None,
            default_flow_style=False,
            sort_keys=False
        )
        doc_file.write(license_comment + doc_string)
