import sys
import argparse
import ctypes
import time
from ipaddress import IPv4Address
from influxdb import InfluxDBClient
from bcc import BPF

MAX_INT_HOP = 4
INT_DST_PORT = 9555
FLOW_LATENCY_THRESHOLD = 50 
HOP_LATENCY_THRESHOLD = 5
LINK_LATENCY_THRESHOLD = 5
QUEUE_OCCUPANCY_THRESHOLD = 1
        
INFLUX_HOST = '10.0.128.1'
INFLUX_DB = 'int'

class Event(ctypes.Structure):
    _fields_ = [
        ("src_ip",          ctypes.c_uint32),
        ("dst_ip",          ctypes.c_uint32),
        ("src_port",        ctypes.c_ushort),
        ("dst_port",        ctypes.c_ushort),
        ("ip_proto",        ctypes.c_ushort),

        ("hop_cnt",         ctypes.c_ubyte),

        ("flow_latency",    ctypes.c_uint32),
        ("switch_ids",      ctypes.c_uint32 * MAX_INT_HOP),
        ("ingress_ports",   ctypes.c_uint16 * MAX_INT_HOP),
        ("egress_ports",    ctypes.c_uint16 * MAX_INT_HOP),
        ("hop_latencies",   ctypes.c_uint32 * MAX_INT_HOP),
        ("queue_ids",       ctypes.c_uint32 * MAX_INT_HOP),
        ("queue_occups",    ctypes.c_uint32 * MAX_INT_HOP),
        ("ingress_tstamps", ctypes.c_uint32 * MAX_INT_HOP),
        ("egress_tstamps",  ctypes.c_uint32 * MAX_INT_HOP),
        ("egress_tx_util",  ctypes.c_uint32 * MAX_INT_HOP),

        ("e_new_flow",      ctypes.c_ubyte),
        ("e_flow_latency",  ctypes.c_ubyte),
        ("e_sw_latency",    ctypes.c_ubyte),
        ("e_link_latency",  ctypes.c_ubyte),
        ("e_q_occupancy",   ctypes.c_ubyte)
    ]

class Collector:

    def __init__(self):
        self.xdp_collector = BPF(src_file="xdp_report_collector.c", debug=0,
            cflags=[
                "-w",
                "-D_MAX_INT_HOP=%s" % MAX_INT_HOP,
                "-D_INT_DST_PORT=%s" % INT_DST_PORT,
                "-D_FLOW_LATENCY_THRESHOLD=%s" % FLOW_LATENCY_THRESHOLD,
                "-D_HOP_LATENCY_THRESHOLD=%s" % HOP_LATENCY_THRESHOLD,
                "-D_LINK_LATENCY_THRESHOLD=%s" % LINK_LATENCY_THRESHOLD,
                "-D_QUEUE_OCCUPANCY_THRESHOLD=%s" % QUEUE_OCCUPANCY_THRESHOLD,
            ])
        self.collector_fn = self.xdp_collector.load_func("report_collector", BPF.XDP)
        
        self.ifaces = []

        self.tb_flow = self.xdp_collector.get_table("tb_flow")
        self.tb_switch = self.xdp_collector.get_table("tb_switch")
        self.tb_link = self.xdp_collector.get_table("tb_link")
        self.tb_queue = self.xdp_collector.get_table("tb_queue")

        self.influx_client = InfluxDBClient(host=INFLUX_HOST,
                                            database=INFLUX_DB)

    def graphite_send(self, metrics):
        payload = pickle.dumps(metrics, protocol=2)
        header = struct.pack("!L", len(payload))
        message = header + payload
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((GRAPHITE_HOST, GRAPHITE_PORT))
            s.sendall(message)
        except Exception as e:
            print(e)
        else:
            s.close()

    def attach_iface(self, iface):
        self.ifaces.append(iface)
        self.xdp_collector.attach_xdp(iface, self.collector_fn)

    def detach_all_ifaces(self):
        for iface in self.ifaces:
            self.xdp_collector.remove_xdp(iface, 0)
        self.ifaces = []

    def open_events(self):
        def _process_event(ctx, data, size):
            event = ctypes.cast(data, ctypes.POINTER(Event)).contents
            print("Received packet")
            print(event.e_new_flow, event.e_sw_latency,
                event.e_q_occupancy, event.e_link_latency)
            print(event.src_ip, event.dst_ip, event.src_port,
                event.dst_port, event.ip_proto)

            metric_timestamp = int(time.time()*1000000000)
            metrics = []
            if event.e_new_flow:
                metrics.append({
                    'measurement': 'flow_latency',
                    'tags': {
                        'src_ip': str(IPv4Address(event.src_ip)),
                        'dst_ip': str(IPv4Address(event.dst_ip)),
                        'src_port': event.src_port,
                        'dst_port': event.dst_port,
                        'protocol': event.ip_proto
                    },
                    'time': metric_timestamp,
                    'fields': {
                        'value': event.flow_latency
                    }
                })


            if event.e_flow_latency:
                metrics.append({
                    'measurement': 'flow_latency',
                    'tags': {
                        'src_ip': event.src_ip,
                        'dst_ip': event.dst_ip,
                        'src_port': event.src_port,
                        'dst_port': event.dst_port,
                        'protocol': event.ip_proto
                    },
                    'time': metric_timestamp,
                    'fields': {
                        'value': event.flow_latency
                    }
                })
                
            if event.e_sw_latency:
                for i in range(event.hop_cnt):
                    metrics.append({
                        'measurement': 'switch_latency',
                        'tags': {
                            'switch_id': event.switch_ids[i]
                        },
                        'time': event.egress_tstamps[i]*1000,
                        'fields': {
                            'value': event.hop_latencies[i]
                        }
                    })

            if event.e_q_occupancy:
                for i in range(event.hop_cnt):
                    metrics.append({
                        'measurement': 'queue_occupancy',
                        'tags': {
                            'switch_id': event.switch_ids[i],
                            'queue_id': event.queue_ids[i]
                        },
                        'time': event.egress_tstamps[i]*1000,
                        'fields': {
                            'value': event.queue_occups[i]
                        }
                    })
            
            if event.e_link_latency:
                for i in range(event.hop_cnt - 1):
                    metrics.append({
                        'measurement': 'link_latency',
                        'tags': {
                            'egress_switch_id': event.switch_ids[i+1],
                            'egress_port_id': event.egress_ports[i+1],
                            'ingress_switch_id': event.switch_ids[i],
                            'ingress_port_id': event.ingress_ports[i]
                        },
                        'time': metric_timestamp,
                        'fields': {
                            'value': abs(event.egress_tstamps[i+1] - event.ingress_tstamps[i])
                        }
                    })
            
            self.influx_client.write_points(points=metrics, protocol="json")

        self.xdp_collector["events"].open_perf_buffer(_process_event, page_cnt=512)
        
    def poll_events(self):
        self.xdp_collector.perf_buffer_poll()

########

if __name__ == "__main__":
    # handle arguments
    parser = argparse.ArgumentParser(description='INT collector.')
    parser.add_argument("iface")
    args = parser.parse_args()
    
    collector = Collector()

    print("Attaching interface")
    collector.attach_iface(sys.argv[1])
    collector.open_events()
    print("eBPF loaded")
    try:
        while True:
            collector.poll_events()
    except KeyboardInterrupt:
        pass

    finally:
        collector.detach_all_ifaces()
        print("Detaching interfaces")
    
    print("Exitting...")
