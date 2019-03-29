from queue import Queue


def init():
    global block_queue, registered_txs

    block_queue = Queue()
    registered_txs = dict()
