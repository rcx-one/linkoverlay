# Ansible Collection - rcx\_one.linkoverlay

This collections provides modules and roles to manage "overlay directories" and to create symlinks into these directories effectively overlaying the directories onto another filesystem tree.

The prime example for this is a central dotfiles directory managed by multiple ansible roles or playbooks that should be overlaid onto the users home directory.

Using the journal callback plugin:

    - hosts: machines
      vars:
        host_journal_path: "/tmp/{{ ansible_facts['ansible_hostname'] }}.journal"
      tasks:
        - name: Copy config file
          ansible.builtin.copy:
            src: /srv/config.cfg
            dest: /home/user/.dotfiles/config.cfg
          vars:
            journal_path: "{{ host_journal_path }}"

        - name: Create another config file
          ansible.builtin.template:
            src: /srv/templated-config.cfd.j2
            dest: /home/user/.dotfiles/templated-config.cfg
          vars:
            journal_path: "{{ host_journal_path }}"

        - name: Remove all files from .dotfiles that we did not just create
          rcx_one.linkoverlay.clean:
            path: "$HOME/.dotfiles"
            exclude: "{{ lookup('ansible.builtin.file', host_journal_path).splitlines() }}"

        - name: Remove temporary local journal file
          ansible.builtin.file:
            path: "{{ journal_path }}"
            state: absent
          delegate_to: localhost

        - name: Overlay .dotfiles onto home
          rcx_one.linkoverlay.linkoverlay:
            base_dir: "$HOME"
            overlay_dir: "$HOME/.dotfiles"

Or using the journal role:

    - hosts: machines
      vars:
        host_journal_path: "/tmp/{{ ansible_facts['ansible_hostname'] }}.journal"
      tasks:
        - name: Copy config file
          ansible.builtin.copy:
            src: /srv/config.cfg
            dest: /home/user/.dotfiles/config.cfg
          register: copy_result

        - name: Create another config file
          ansible.builtin.template:
            src: /srv/templated-config.cfd.j2
            dest: /home/user/.dotfiles/templated-config.cfg
          register: template_result

        - name: Log files to journal
          include_role:
            - name: rcx_one.linkoverlay.journal
          vars:
            journal_path: "{{ host_journal_path }}"
            result:
              - "{{ copy_result }}"
              - "{{ template_result }}"

        - name: Remove all files from .dotfiles that we did not just create
          rcx_one.linkoverlay.clean:
            path: "$HOME/.dotfiles"
            exclude: "{{ lookup('ansible.builtin.file', host_journal_path).splitlines() }}"

        - name: Remove temporary local journal file
          ansible.builtin.file:
            path: "{{ journal_path }}"
            state: absent
          delegate_to: localhost

        - name: Overlay .dotfiles onto home
          rcx_one.linkoverlay.linkoverlay:
            base_dir: "$HOME"
            overlay_dir: "$HOME/.dotfiles"

