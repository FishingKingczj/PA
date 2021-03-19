# -------- constant and config --------
# states of MSI protocol
STATE_INV = "I" # invalid for cache, not cached for dir
STATE_SHA = "S"
STATE_MOD = "M"
# flag to mark null tag
UNUSED_TAG = -1

# processor number
PROCESSOR_NUM = 4
# size of processor private cache
CACHE_SIZE = 512
# size of directory (memory) space
DIRECT_SIZE = 2 ** 64
# size of cache block
BLOCK_SIZE = 4
# optimize option
DIRECT_OPTIMIZE = False

# latency
CACHE_PROBE_LATENCY = 1
CACHE_ACCESS_LATENCY = 1
SRAM_ACCESS_LATENCY = 1
DIRECTORY_ACCESS_LATENCY = 1
PROCESSORS_HOP_LATENCY = 3
DIRECTORY_HOP_LATENCY = 5
MEMORY_ACCESS_LATENCY = 15
WRITE_BACKE_LATENCY = 0

# -------- inner structure --------
# i-th item means the P_i processor
# each processor is a cache which has CACHE_SIZE of Block
PROS = []
# dict to store memory line in directory
DIRECT = {}
DIRECT_CACHE = None

# -------- statics --------
class Statics:
    # log info of current access
    curr_log = ""
    # access type
    access_type = -1
    PRIV_TYPE = 0
    REMOTE_TYPE = 1
    OFF_TYPE = 2
    # line-by-line explanation switch
    log_switch = False

    # updated statics, final result should be calculated by statics()
    Private_accesses = 0
    Remote_accesses = 0
    Off_chip_accesses = 0
    Total_accesses = 0
    Replacement_writebacks = 0
    Coherence_writebacks = 0
    Invalidations_sent = 0
    # Average-latency
    # Priv-average-latency
    # Rem-average-latency
    # Off-chip-average-latency
    Priv_latency = 0
    Rem_latency = 0
    Off_chip_latency = 0
    Total_latency = 0
    On_chip_accesses = 0
    Distance = 0

# global statics object
statics = Statics()

# -------- interface function --------
# init the simulator state
def init_simulator(optimize):
    # init processors
    for i in range(PROCESSOR_NUM):
        # i-th item means the index_i cache block in private cache
        cache = []
        for j in range(CACHE_SIZE):
            cache.append(Block(j))
        PROS.append(cache)

    global DIRECT_CACHE, DIRECT_OPTIMIZE
    if optimize:
        DIRECT_CACHE = CacheQueue(512)
        DIRECT_OPTIMIZE = True

# run one operation, return the success state
def run_operation(processor, operation, addr):
    # verify value
    if processor >= PROCESSOR_NUM:
        print("processor value error")
        return False
    if addr > DIRECT_SIZE:
        print("directory value error")
        return False
    # clear log buffer
    statics.curr_log = ""

    # start operation
    latency = 0
    log("P%d %s word %d" % (processor, "read" if operation=="R" else "write", addr))

    # cache prob
    latency += CACHE_PROBE_LATENCY
    index, tag = address2cache(addr)
    log("search cache tag %d in block %d" % (tag, index))

    if operation == "R":
        latency += read(processor, index, tag)
    elif operation == "W":
        latency += write(processor, index, tag)
    else:
        print("operation value error")
        return False
    log("\nTotal latency: %d cycles" % latency)

    # update statics
    statics.Total_accesses += 1
    statics.Total_latency += latency
    if statics.access_type == statics.PRIV_TYPE:
        statics.Private_accesses += 1
        statics.Priv_latency += latency
    elif statics.access_type == statics.REMOTE_TYPE:
        statics.Remote_accesses += 1
        statics.Rem_latency += latency
    elif statics.access_type == statics.OFF_TYPE:
        statics.Off_chip_accesses += 1
        statics.Off_chip_latency += latency

    # log output
    if statics.log_switch:
        print(statics.curr_log)
    return True

def output_v():
    statics.log_switch = not statics.log_switch

def output_p():
    for i in range(PROCESSOR_NUM):
        pro = PROS[i]
        print("P%d" % i)
        for j in range(CACHE_SIZE):
            if pro[j].tag != UNUSED_TAG:
                print(j, pro[j].tag, pro[j].state)

def output_h():
    hit_rate = statics.Private_accesses / statics.Total_accesses
    print("%d / %d accesses hit, hit rate: %.2f"
          % (statics.Private_accesses, statics.Total_accesses, hit_rate))

# -------- control function --------
def read(processor, index, tag):
    latency = 0
    cache_tag = PROS[processor][index].tag
    cache_state = PROS[processor][index].state
    new_state = STATE_SHA

    # cache hit, state should be S or M
    if cache_tag == tag and cache_state != STATE_INV:
        log("read hit with state %s, read from local cache" % cache_state)
        latency += CACHE_ACCESS_LATENCY
        # set private access type
        statics.access_type = statics.PRIV_TYPE
    else:
        # tag miss
        if cache_tag != tag:
            log("tag miss for local cache with state %s" % cache_state)
            # query data from directory
            latency += directory_query(processor, index, tag, new_state)

            # write back to directory
            # no count for latency, just update directory and notify
            if cache_tag != UNUSED_TAG:
                # write back original cached address
                cache_addr = cache_tag * CACHE_SIZE + index
                # ignore the latency
                set_dict(processor, cache_addr, STATE_INV)
        # cache state miss (I)
        else:
            log("state miss with state I")
            # query data from directory
            latency += directory_query(processor, index, tag, new_state)
    return latency

def write(processor, index, tag):
    latency = 0
    cache_tag = PROS[processor][index].tag
    cache_state = PROS[processor][index].state
    new_state = STATE_MOD

    # write cache hit
    if cache_tag == tag and cache_state == STATE_MOD:
        log("find write hit with state M, write to local cache")
        latency += CACHE_ACCESS_LATENCY
        # set private access type
        statics.access_type = statics.PRIV_TYPE
    else:
        # tag miss
        if cache_tag != tag:
            log("tag miss for local cache with state %s" % cache_state)
            # query data from directory
            latency += directory_query(processor, index, tag, new_state)

            # write back to directory
            # no count for latency, just update directory and notify
            if cache_tag != UNUSED_TAG:
                # write back original cached address
                cache_addr = cache_tag * CACHE_SIZE + index
                # ignore the latency
                set_dict(processor, cache_addr, STATE_INV)
        # cache state miss (I or S)
        else:
            log("state miss with state %s" % cache_state)
            # query data from directory
            latency += directory_query(processor, index, tag, new_state)

    return latency

# query data from directory
def directory_query(processor, index, tag, new_state):
    latency = 0
    b_addr = tag * CACHE_SIZE + index
    # set type as remote
    statics.access_type = statics.REMOTE_TYPE

    if not DIRECT_OPTIMIZE:
        # send message to dict and search in directory
        latency += DIRECTORY_HOP_LATENCY + DIRECTORY_ACCESS_LATENCY
    # directory cache on
    else:
        # send message to SRAM cache and search in directory
        latency += SRAM_ACCESS_LATENCY + DIRECTORY_ACCESS_LATENCY
        # line record not in the cache, or cache need data from memory
        if not DIRECT_CACHE.find(b_addr) or DIRECT[b_addr].state == STATE_INV:
            # need to send message to directory for target record
            # the directory search target record and send it to the cache
            # directory and cache update latency can be overlapped
            latency += DIRECTORY_HOP_LATENCY + DIRECTORY_ACCESS_LATENCY
            DIRECT_CACHE.push(b_addr)
        # line record in the cache
        else:
            log("line record in the directory cache")

    # no sharer in directory
    if b_addr not in DIRECT or DIRECT[b_addr].state == STATE_INV:
        log("no sharer in directory")
        # query data from memory
        latency += memory_query()
    else:
        # find sharer in directory
        sharer = sharing_vector(processor, b_addr)
        latency += forward_lines(processor, sharer, index, new_state)

    # set directory state and
    # update state and data in local cache
    latency += parallel_run([
            processor_update_state(processor, index, new_state) +
            processor_update_data(processor, index, tag),
            set_dict(processor, b_addr, new_state)
        ])

    return latency

# parallel run events and overlap the latency of shorter events
def parallel_run(events):
    max_latency = 0
    for e in events:
        if e > max_latency:
            max_latency = e
    return max_latency

# query data from memory and send to processor
def memory_query():
    log("fetch data from memory")
    latency = MEMORY_ACCESS_LATENCY + DIRECTORY_HOP_LATENCY
    if DIRECT_OPTIMIZE:
        latency += SRAM_ACCESS_LATENCY
    statics.access_type = statics.OFF_TYPE
    return latency

# processor update state
def processor_update_state(processor, index, new_state):
    PROS[processor][index].state = new_state
    return CACHE_PROBE_LATENCY

# processor update tag
def processor_update_data(processor, index, tag):
    PROS[processor][index].tag = tag
    return CACHE_ACCESS_LATENCY

# get the sharing remote processors
def sharing_vector(processor, addr):
    res = []
    vec = DIRECT[addr].share
    for i in range(PROCESSOR_NUM):
        if vec[i] != STATE_INV:
            if processor != i:
                log("find state %s in the cache of P%d" % (vec[i], i))
            res.append(i)
    return res

# directory sends message to processor to forward the line
def forward_lines(processor, sharers, index, new_state):
    # find the closest sharer
    closest = sharers[0]
    for share in sharers:
        if p_distance(share, processor) < p_distance(closest, processor):
            closest = share

    latency = 0
    # directory send message to processors
    latency += DIRECTORY_HOP_LATENCY if not DIRECT_OPTIMIZE else SRAM_ACCESS_LATENCY
    if closest != processor:
        log("P%d send data to P%d" % (closest, processor))

    # Share, only closest sharer need to send message
    if new_state == STATE_SHA:
        latency += share_data(closest, processor, index, new_state)

    # Modified, need to send IACK to processor
    elif new_state == STATE_MOD:
        events = []
        # closest sharer need to send message and IACK
        if processor != closest:
            events.append(share_data(closest, processor, index, new_state))
        # other sharers need to match and send IACK
        for share in sharers:
            if share != processor:
                events.append(send_IACK(share, processor))
        if len(events) == 0:
            log("write to local cache")
        latency += parallel_run(events)
    return latency

# send message from sharer to processor
def send_message(from_p, to_p):
    statics.On_chip_accesses += 1
    statics.Distance += p_distance(from_p, to_p)
    return p_distance(from_p, to_p) * PROCESSORS_HOP_LATENCY

# get and send data from sharer to processor
def share_data(from_p, to_p, index, new_state):
    # read the data
    latency = CACHE_ACCESS_LATENCY
    # update cache state
    if new_state == STATE_SHA:
        latency += processor_update_state(from_p, index, STATE_SHA)
    elif new_state == STATE_MOD:
        latency += processor_update_state(from_p, index, STATE_INV)
    # send data
    latency += send_message(from_p, to_p)
    return latency

# send message from sharer to processor
def send_IACK(from_p, to_p):
    log("P%d send IACK to P%d" % (from_p, to_p))
    # add one Invalidation (IACK)
    statics.Invalidations_sent += 1
    return CACHE_PROBE_LATENCY + send_message(from_p, to_p)

def set_dict(processor, addr, new_state):
    # new record
    if addr not in DIRECT:
        DIRECT[addr] = Line(addr)
        DIRECT[addr].state = new_state
        DIRECT[addr].share[processor] = new_state
    else:
        # set to Modified
        if new_state == STATE_MOD:
            # other Share state should be Invalid
            for i in range(PROCESSOR_NUM):
                DIRECT[addr].share[i] = STATE_INV
            DIRECT[addr].state = STATE_MOD
            DIRECT[addr].share[processor] = STATE_MOD
        # set to Share
        if new_state == STATE_SHA:
            DIRECT[addr].state = STATE_SHA
            DIRECT[addr].share[processor] = STATE_SHA
            # Modified state should change to Share (with coherence write back)
            log("change state M to S, write back data to memory")
            statics.Coherence_writebacks += 1
            for i in range(PROCESSOR_NUM):
                if DIRECT[addr].share[i] == STATE_MOD:
                    DIRECT[addr].share[i] = STATE_SHA
        # set to Invalid (with replacement write back)
        if new_state == STATE_INV:
            log("replace local cache, write back data to memory")
            statics.Replacement_writebacks += 1
            DIRECT[addr].share[processor] = STATE_INV
            # if there are no sharer on chip, set line state to Invalid
            new_dict_state = STATE_INV
            for s in DIRECT[addr].share:
                if s != STATE_INV:
                    new_dict_state = s
            DIRECT[addr].state = new_dict_state
    return DIRECTORY_ACCESS_LATENCY

# -------- tool function --------
# map memory address to cache block (index, tag)
def address2cache(address):
    b_address = address // BLOCK_SIZE
    index = b_address % CACHE_SIZE
    tag = b_address // CACHE_SIZE
    return index, tag

# hop distance from from_p to to_p
def p_distance(from_p, to_p):
    if from_p <= to_p:
        return to_p - from_p
    else:
        return PROCESSOR_NUM - (from_p - to_p)

def log(text):
    if statics.curr_log != "":
        statics.curr_log += ", "
    statics.curr_log += text

# return the full report
def report_statics():
    result = \
    "Private-accesses: %d\n" \
    "Remote-accesses: %d\n" \
    "Off-chip-accesses: %d\n" \
    "Total-accesses: %d\n" \
    "Replacement-writebacks: %d\n" \
    "Coherence-writebacks: %d\n" \
    "Invalidations-sent: %d\n" \
    "Average-latency: %.2f\n" \
    "Priv-average-latency: %.2f\n" \
    "Rem-average-latency: %.2f\n" \
    "Off-chip-average-latency: %.2f\n" \
    "On-chip-average-distance: %.2f\n" \
    "Total-latency: %d" \
    % (statics.Private_accesses,
       statics.Remote_accesses,
       statics.Off_chip_accesses,
       statics.Total_accesses,
       statics.Replacement_writebacks,
       statics.Coherence_writebacks,
       statics.Invalidations_sent,
       0 if statics.Total_accesses == 0 else statics.Total_latency / statics.Total_accesses,
       0 if statics.Private_accesses == 0 else statics.Priv_latency / statics.Private_accesses,
       0 if statics.Remote_accesses == 0 else statics.Rem_latency / statics.Remote_accesses,
       0 if statics.Off_chip_accesses == 0 else statics.Off_chip_latency / statics.Off_chip_accesses,
       0 if statics.On_chip_accesses == 0 else statics.Distance / statics.On_chip_accesses,
       statics.Total_latency)
    return result

# -------- basic data structures --------
# processor cache block structure
class Block:
    def __init__(self, index):
        self.index = index
        # tag of cache block
        self.tag = UNUSED_TAG
        # cache state
        self.state = STATE_INV

# directory line structure
class Line:
    def __init__(self, index):
        self.index = index
        # line state
        self.state = STATE_INV
        # processor sharing vector
        self.share = []
        for i in range(PROCESSOR_NUM):
            self.share.append(STATE_INV)

# -------- optimize --------
class CacheQueue:
    size = 0
    cache = []

    def __init__(self, _size):
        self.size = _size

    def push(self, index):
        self.cache.append(index)
        if len(self.cache) > self.size:
            self.cache.remove(self.cache[0])

    def find(self, index):
        return index in self.cache