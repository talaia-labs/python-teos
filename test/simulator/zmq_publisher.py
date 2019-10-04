import zmq


class ZMQPublisher:
    def __init__(self, topic, feed_protocol, feed_addr, feed_port):
        self.topic = topic
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("%s://%s:%s" % (feed_protocol, feed_addr, feed_port))

    def publish_data(self, data):
        self.socket.send_multipart([self.topic, data])
