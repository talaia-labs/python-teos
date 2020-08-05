Protos for `teos` to manage the communication between the `HTTP_API` and the `RPC_API` with the `INTERNAL_API`.

![gRPC teos](https://user-images.githubusercontent.com/6665628/89121491-ac226a00-d4bf-11ea-8db1-3092e3ffe5f4.png)


## Compile protos

Protos can be compiled using:

```
python -m grpc_tools.protoc -I=teos/protobuf/protos --python_out=teos/protobuf --grpc_python_out=teos/protobuf teos/protobuf/protos/*.proto
```

### Things to consider

`user_pb2_grpc.py` and `appointment_pb2_grpc.py` need to be deleted given they are basically empty.

Currently, `teos.protobuf` is not prepended to the imports that need it for `pb2` files, e.g.

```
import appointment_pb2 as appointment__pb2
import user_pb2 as user__pb2
```

is generated instead of

```
import teos.protobuf.appointment_pb2 as appointment__pb2
import teos.protobuf.user_pb2 as user__pb2
```

