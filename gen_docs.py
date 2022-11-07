#!/usr/bin/env python3
from library.link_overlay import MODULE_ARGS
from yaml import safe_dump, safe_load


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


if __name__ == "__main__":
    docs = [
        {
            name: {
                key: val
                for key, val in doc.items()
                if key in documented_keys
            }
        }
        for name, doc in MODULE_ARGS.items()
    ]
    with open("link_overlay.partial.yml") as doc_partial:
        doc_yml = safe_load(doc_partial)
    doc_yml["DOCUMENTATION"]["options"] = docs
    with open("library/link_overlay.yml", "w") as doc_file:
        safe_dump(doc_yml, doc_file, default_flow_style=False)
