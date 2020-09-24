import sys
import json
from test.teos.conftest import get_random_value_hex
from contrib.client.teos_client import main as teos_client

appointment_data = {
    "tx": "4615a58815475ab8145b6bb90b1268a0dbb02e344ddd483f45052bec1f15b1951c1ee7f070a0993da395a5ee92ea3a1c184b5ffdb250"
    "7164bf1f8c1364155d48bdbc882eee0868ca69864a807f213f538990ad16f56d7dfb28a18e69e3f31ae9adad229e3244073b7d643b4597ec88"
    "bf247b9f73f301b0f25ae8207b02b7709c271da98af19f1db276ac48ba64f099644af1ae2c90edb7def5e8589a1bb17cc72ac42ecf07dd29cf"
    "f91823938fd0d772c2c92b7ab050f8837efd46197c9b2b3f",
    "tx_id": "0af510d92a50c1d67c6f7fc5d47908d96b3eccdea093d89bcbaf05bcfebdd982",
    "to_self_delay": 20,
}

# Add too many appointment by changing the tx_id (100 is the default max)
for _ in range(int(sys.argv[1])):
    appointment_data["tx_id"] = get_random_value_hex(32)
    teos_client("add_appointment", [json.dumps(appointment_data)], {})
