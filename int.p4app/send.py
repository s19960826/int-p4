#!/usr/bin/python

# Copyright 2013-present Barefoot Networks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from scapy.all import Ether, IP, sendp, get_if_hwaddr, get_if_list, TCP, Raw, UDP
import sys
import time
import random, string

def randomword(max_length):
    length = random.randint(1, max_length)
    return ''.join(random.choice(string.lowercase) for i in range(length))

def read_topo():
    nb_hosts = 0
    nb_switches = 0
    links = []
    with open("topo.txt", "r") as f:
        line = f.readline()[:-1]
        w, nb_switches = line.split()
        assert(w == "switches")
        line = f.readline()[:-1]
        w, nb_hosts = line.split()
        assert(w == "hosts")
        for line in f:
            if not f: break
            a, b = line.split()
            links.append( (a, b) )
    return int(nb_hosts), int(nb_switches), links

def send_random_traffic(dst):
    dst_mac = None
    dst_ip = None
    iface = [i for i in get_if_list() if 'eth0' in i][0]
    src_mac = [get_if_hwaddr(i) for i in get_if_list() if 'eth0' in i]
    if len(src_mac) < 1:
        print ("No interface for output")
        sys.exit(1)
    src_mac = src_mac[0]
    src_ip = None
    if src_mac =="00:00:00:00:01:01":
        src_ip = "10.0.1.1"
    elif src_mac =="00:00:00:00:02:02":
        src_ip = "10.0.2.2"
    elif src_mac =="00:00:00:00:03:03":
        src_ip = "10.0.3.3"
    elif src_mac =="00:00:00:00:04:04":
        src_ip = "10.0.4.4"
    else:
        print ("Invalid source host")
        sys.exit(1)

    if dst == 'h1':
        dst_mac = "00:00:00:00:01:01"
        dst_ip = "10.0.1.1"
    elif dst == 'h2':
        dst_mac = "00:00:00:00:02:02"
        dst_ip = "10.0.2.2"
    elif dst == 'h3':
        dst_mac = "00:00:00:00:03:03"
        dst_ip = "10.0.3.3"
    elif dst == 'h4':
        dst_mac = "00:00:00:00:04:04"
        dst_ip = "10.0.4.4"
    else:
        print ("Invalid host to send to")
        sys.exit(1)

    total_pkts = 0
    random_ports = random.sample(xrange(1024, 65535), 11)
    t1 = time.time()
    for port in random_ports:
        num_packets = random.randint(50, 250)
        # num_packets = 1
        for i in range(num_packets):
            data = randomword(100)
            # data = randomword(1)
            p = Ether(dst=dst_mac,src=src_mac)/IP(dst=dst_ip,src=src_ip)
            p = p/UDP(dport=port)/Raw(load=data)
            # p = p/TCP(dport=port)/Raw(load=data)
            # print p.show()
            sendp(p, iface = iface, verbose=False)
            total_pkts += 1
    t2 = time.time()
    print "Sent %s packets in total" % total_pkts
    print "Packets per second: %f" % (total_pkts/(t2-t1))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python send.py dst_host_name")
        sys.exit(1)
    else:
        dst_name = sys.argv[1]
        send_random_traffic(dst_name)
