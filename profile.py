import os

import geni.portal as portal
import geni.rspec.pg as pg
import geni.rspec.igext as ig
import geni.rspec.emulab as emulab
import geni.rspec.emulab.ansible

from geni.rspec.emulab.ansible import Role, RoleBinding, Override, Playbook


HEAD_CMD = "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c 'EMULAB_ANSIBLE_NOAUTO=1 /local/repository/emulab-ansible-bootstrap/head.sh >/local/logs/setup.log 2>&1'"
TAIL_CMD = "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c '/local/setup/ansible/run-automation.sh >> /local/logs/setup.log 2>&1'"
CLIENT_CMD = "sudo -u `geni-get user_urn | cut -f4 -d+` -Hi /bin/sh -c '/local/repository/emulab-ansible-bootstrap/client.sh >/local/logs/setup.log 2>&1'"
UBUNTU_IMG = "urn:publicid:IDN+emulab.net+image+emulab-ops//UBUNTU22-64-STD"
ANSIBLE_VENV = "/local/setup/venv/default/bin"
ANSIBLE_COLLECTIONS_DIR = "~/.ansible/collections/ansible_collections"
NEXTG_UTILS_COLLECTION_NS = "dustinmaas/nextg_utils"
NEXTG_UTILS_COLLECTION_REPO = "git+https://gitlab.flux.utah.edu/dmaas/ansible-nextg"
GALAXY_INSTALL_CMD = "{}/ansible-galaxy collection install {} >> /local/logs/setup.log 2>&1".format(ANSIBLE_VENV, NEXTG_UTILS_COLLECTION_REPO)
GALAXY_INSTALL_REQS_CMD = "{}/ansible-galaxy install -r {}/{}/requirements.yml >> /local/logs/setup.log 2>&1".format(ANSIBLE_VENV, ANSIBLE_COLLECTIONS_DIR, NEXTG_UTILS_COLLECTION_NS)

pc = portal.Context()
node_types = [
    ("d430", "Emulab, d430"),
    ("d740", "Emulab, d740"),
]

pc.defineParameter(
    name="deployric",
    description="Deploy ORAN SC RIC and xApp on the same node.",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=False,
)
pc.defineParameter(
    name="nodetype",
    description="Type of compute node to used.",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],
    legalValues=node_types,
    advanced=True,
)

pc.defineParameter(
    name="do_deploy",
    description="Run deploy scripts for srsRAN_Project and srsRAN_4G",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True,
    advanced=True,
)

pc.defineParameter(
    name="enable_vnc",
    description="Enable browser-based VNC server.",
    typ=portal.ParameterType.BOOLEAN,
    defaultValue=True,
    advanced=True,
)

params = pc.bindParameters()

tourDescription = """

### srsRAN 5G with Open5GS and Simulated RF

This profile instantiates a single-node experiment for running and end to end 5G network using srsRAN_Project 24.10 (gNodeB), srsRAN_4G 23.11 (UE), and Open5GS (in container) with IQ samples passed via ZMQ between the gNodeB and the UE. It requires a single Dell d430 compute node.

Optionally, you can also deploy a containerized ORAN SC RIC and xApp on the same node to demonstrate a 5G RAN Intelligent Controller (RIC) and xApp interacting with the gNodeB.

"""
tourInstructions = """

Startup scripts will still be running when your experiment becomes ready. Watch the "Startup" column on the "List View" tab for your experiment and wait until all of the compute nodes show "Finished" before proceeding.

Note: You will be opening several SSH sessions on a single node. Using a terminal multiplexing solution like `screen` or `tmux`, both of which are installed on the image for this profile, is recommended.

After all startup scripts have finished...

In an SSH session on `node`:

```
# create a network namespace for the UE
sudo ip netns add ue1

# start the Open5GS container
cd /opt/srsRAN_Project/docker
sudo docker compose up 5gc
```

"""

if params.deployric:
    tourInstructions += \
    """
In another session

```
# start the ORAN SC RIC container
cd /opt/oran-sc-ric
sudo docker compose up
```

    """

tourInstructions += \
    """
In another session:

```
# start the gNodeB
sudo /opt/srsRAN_Project/build/apps/gnb/gnb -c /etc/srsran/gnb.yml
```

The AMF logs in the 5gc container should show a connection from the gNodeB via the N2 interface.

In a forth session:

```
# start the UE
sudo /opt/srsRAN_4G/build/srsue/src/srsue /etc/srsran/ue.conf
```

As the UE attaches to the network, the AMF log and gNodeB process will show progress as a PDU session for the UE is eventually established.

At this point, you should be able to pass traffic across the network via the previously created namespace in yet another session on the same node:

```
# start pinging the Open5GS data network
sudo ip netns exec ue1 ping -i 0.1 10.45.1.1
```

    """

if params.deployric:
    tourInstructions += \
    """
In another session:

```
# start the xApp
cd /opt/oran-sc-ric
sudo docker compose exec python_xapp_runner ./kpm_mon_xapp.py --metrics=DRB.UEThpDl,DRB.UEThpUl --kpm_report_style=5
```

You should see action in the RIC container logs as the KPM monitor xApp recieves metrics from the gNodeB and UE.

    """

tourInstructions += \
    """
Note: When ZMQ is used by srsRAN to pass IQ samples, if you restart either of the `gnb` or `srsue` processes, you must restart the other as well.

You can find more information about the open source 5G software used in this profile at:

https://open5gs.org
https://github.com/srsran/srsRAN_Project
    """

pc.verifyParameters()
request = pc.makeRequestRSpec()
request.addRole(
    Role(
        "single_node_oran",
        path="ansible",
        playbooks=[Playbook("single_node_oran", path="single_node_oran.yml")]
    )
)
request.addOverride(Override("srsran_project_build_5gc", value="true"))

if params.deployric:
    request.addOverride(Override("srsran_project_enable_du_e2", value="true"))
    request.addOverride(Override("srsran_project_e2sm_kpm_enabled", value="true"))

node = request.RawPC("node")
node.hardware_type = params.nodetype
node.disk_image = UBUNTU_IMG
node.bindRole(RoleBinding("single_node_oran"))
node.addService(pg.Execute(shell="sh", command=HEAD_CMD))
node.addService(pg.Execute(shell="sh", command=GALAXY_INSTALL_CMD))
node.addService(pg.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD))
node.addService(pg.Execute(shell="sh", command=TAIL_CMD))
node.startVNC()

tour = ig.Tour()
tour.Description(ig.Tour.MARKDOWN, tourDescription)
tour.Instructions(ig.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
