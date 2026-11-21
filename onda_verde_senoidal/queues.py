from collections import defaultdict
from heapq import heappop, heappush


QUEUE_STOP_SPEED_MPS = 0.1
QUEUE_GAP_M = 10.0


class QueueMonitor:
    def __init__(self, net, approaches):
        lanes = {lane.getID(): lane for edge in net.getEdges(withInternal=True) for lane in edge.getLanes()
                 if lane.allows('passenger') or lane.allows('bus')}
        self.lengths = {lane_id: lane.getLength() for lane_id, lane in lanes.items()}
        self.approaches = approaches
        self.short_approaches = {lane_id for lane_id in approaches if self.lengths[lane_id] <= QUEUE_GAP_M}
        self.upstream = defaultdict(set)
        for lane_id, lane in lanes.items():
            for connection in lane.getOutgoing():
                downstream = connection.getViaLaneID() or connection.getToLane().getID()
                if downstream in lanes:
                    self.upstream[downstream].add(lane_id)

    def measure(self, stopped):
        """Return the longest stopped queue in meters for each monitored junction."""
        queues = defaultdict(float)
        if stopped:
            for vehicles in stopped.values():
                vehicles.sort()
            for lane_id in (self.approaches.keys() & stopped.keys()) | self.short_approaches:
                length = self._extent(lane_id, stopped)
                if length:
                    node_id, _ = self.approaches[lane_id]
                    queues[node_id] = max(queues[node_id], length)
        return queues

    def _extent(self, root, stopped):
        pending = [(0.0, root, -QUEUE_GAP_M)]
        visited = set()
        longest = 0.0
        while pending:
            offset, lane_id, negative_gap = heappop(pending)
            if lane_id in visited:
                continue
            reach = -negative_gap
            connected = False
            for front, rear in stopped.get(lane_id, ()):
                if front > reach:
                    break
                connected = True
                longest = max(longest, offset+rear)
                reach = max(reach, rear+QUEUE_GAP_M)
            length = self.lengths[lane_id]
            if connected or reach >= length:
                # Keep the nearest continuous path to each lane and avoid counting cycles.
                visited.add(lane_id)
            if reach >= length:
                for upstream in self.upstream.get(lane_id, ()):
                    if upstream not in visited:
                        heappush(pending, (offset+length, upstream, length-reach))
        return longest
