import os

import geni.portal as portal
import geni.rspec.pg as pg
import geni.rspec.igext as ig
import geni.rspec.emulab as emulab
import geni.rspec.emulab.ansible

from geni.rspec.emulab.ansible import Role, RoleBinding, Override, Playbook


tourDescription = """

### srsRAN 5G with Open5GS and Simulated RF

This profile instantiates a single-node experiment for running and end to end 5G network using srsRAN_Project 23.5 (gNodeB), srsRAN_4G (UE), and Open5GS with IQ samples passed via ZMQ between the gNodeB and the UE. It requires a single Dell d430 compute node.

"""
tourInstructions = """

Startup scripts will still be running when your experiment becomes ready. Watch the "Startup" column on the "List View" tab for your experiment and wait until all of the compute nodes show "Finished" before proceeding.

Note: You will be opening several SSH sessions on a single node. Using a terminal multiplexing solution like `screen` or `tmux`, both of which are installed on the image for this profile, is recommended.

After all startup scripts have finished...

In an SSH session on `node`:

```
# create a network namespace for the UE
sudo ip netns add ue1

# start tailing the Open5GS AMF log
tail -f /var/log/open5gs/amf.log
```

In a second session:

```
# use tshark to monitor 5G core network function traffic
sudo tshark -i lo \
  -f "not arp and not port 53 and not host archive.ubuntu.com and not host security.ubuntu.com and not tcp" \
  -Y "s1ap || gtpv2 || pfcp || diameter || gtp || ngap || http2.data.data || http2.headers"
```

In a third session:

```
# start the gNodeB
sudo gnb -c /etc/srsran/gnb.conf
```

The AMF should show a connection from the gNodeB via the N2 interface and `tshark` will show NG setup/response messages.

In a forth session:

```
# start the UE
sudo srsue
```

As the UE attaches to the network, the AMF log and gNodeB process will show progress and you will see NGAP/NAS traffic in the output from `tshark` as a PDU session for the UE is eventually established.

At this point, you should be able to pass traffic across the network via the previously created namespace in yet another session on the same node:

```
# start pinging the Open5GS data network
sudo ip netns exec ue1 ping 10.45.0.1
```

You can also use `iperf3` to generate traffic. E.g., for downlink, in one session:

```
# start iperf3 server for UE
sudo ip netns exec ue1 iperf3 -s
```

And in another:

```
# start iperf3 client for CN data network
sudo iperf3 -c {ip of UE (indicated in srsue stdout)}
```

Note: When ZMQ is used by srsRAN to pass IQ samples, if you restart either of the `gnb` or `srsue` processes, you must restart the other as well.

You can find more information about the open source 5G software used in this profile at:

https://open5gs.org
https://github.com/srsran/srsRAN_Project
"""


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
    name="nodetype",
    description="Type of compute node to used.",
    typ=portal.ParameterType.STRING,
    defaultValue=node_types[0],
    legalValues=node_types,
    advanced=True,
)

params = pc.bindParameters()
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

node = request.RawPC("node")
node.hardware_type = params.nodetype
node.disk_image = UBUNTU_IMG
node.bindRole(RoleBinding("single_node_oran"))
node.addService(pg.Execute(shell="sh", command=HEAD_CMD))
node.addService(pg.Execute(shell="sh", command=GALAXY_INSTALL_CMD))
node.addService(pg.Execute(shell="sh", command=GALAXY_INSTALL_REQS_CMD))
node.addService(pg.Execute(shell="sh", command=TAIL_CMD))

tour = ig.Tour()
tour.Description(ig.Tour.MARKDOWN, tourDescription)
tour.Instructions(ig.Tour.MARKDOWN, tourInstructions)
request.addTour(tour)

pc.printRequestRSpec(request)
